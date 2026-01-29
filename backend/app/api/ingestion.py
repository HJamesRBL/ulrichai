import json
import re
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from typing import List, Dict, Any
import os
import shutil
from pathlib import Path
import logging
from datetime import datetime

from ..processing.document_processor import processor
from ..processing.graph_builder import graph_builder
from ..processing.video_processor import VideoProcessor
from ..processing.video_chunker import VideoChunker
from ..core.database import db, supabase
from ..core.vector_store import vector_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ingestion"])

# Create uploads directory if it doesn't exist
# Use absolute path to root uploads directory (two levels up from app/api to get to backend, then one more to root)
UPLOAD_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))) / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Form(None),
    chunking_config: str = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload and process a single document or video"""

    # Validate file type
    allowed_types = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'mp4', 'webm', 'mov', 'avi', 'mkv']
    file_ext = file.filename.split('.')[-1].lower()

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type .{file_ext} not supported. Allowed types: {allowed_types}"
        )

    # Parse metadata and chunking config
    logger.info(f"Received metadata string: {metadata}")
    try:
        metadata_dict = json.loads(metadata) if metadata else {}
        chunking_config_dict = json.loads(chunking_config) if chunking_config else {}
        logger.info(f"Parsed metadata_dict: {metadata_dict}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing metadata or chunking config: {e}")
        logger.error(f"Failed metadata string was: {metadata}")
        metadata_dict = {}
        chunking_config_dict = {}

    # Save uploaded file
    file_path = UPLOAD_DIR / f"{datetime.now().timestamp()}_{file.filename}"

    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail="Error saving uploaded file")

    # Determine if this is a video file
    video_extensions = ['mp4', 'webm', 'mov', 'avi', 'mkv']
    is_video = file_ext in video_extensions

    # Process in background - route to appropriate handler
    if is_video:
        background_tasks.add_task(process_video_task, str(file_path), file_ext, file.filename, metadata_dict)
    else:
        background_tasks.add_task(process_document_task, str(file_path), file_ext, file.filename, metadata_dict, chunking_config_dict)

    return {
        "message": f"{'Video' if is_video else 'Document'} uploaded successfully",
        "filename": file.filename,
        "status": "processing"
    }

async def process_document_task(file_path: str, file_type: str, original_filename: str, metadata: Dict[str, Any] = None, chunking_config: Dict[str, Any] = None):
    """Background task to process document"""
    try:
        if metadata is None:
            metadata = {}
        if chunking_config is None:
            chunking_config = {}

        logger.info(f"Starting to process document: {original_filename}")
        logger.info(f"Received metadata: {metadata}")
        logger.info(f"Received chunking config: {chunking_config}")

        # Extract chunking parameters (in characters, not tokens)
        chunk_size = chunking_config.get('chunkSize', 3000)  # Default 3000 chars
        chunk_overlap = chunking_config.get('chunkOverlap', 200)  # Default 200 chars
        preserve_lists = chunking_config.get('preserveLists', True)  # Default True

        # Create processor with custom chunking settings
        from app.processing.document_processor import DocumentProcessor
        custom_processor = DocumentProcessor(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            preserve_lists=preserve_lists
        )

        # Process document with custom chunking
        doc_data = await custom_processor.process_document(file_path, file_type)
        doc_data['title'] = original_filename
        doc_data['filename'] = original_filename
        
        # Generate embeddings for all levels
        logger.info("Generating embeddings...")
        
        # Document-level embedding
        doc_embedding = vector_store.get_embedding(doc_data['summary'])
        
        # Section-level embeddings
        section_embeddings = []
        for section in doc_data['sections']:
            section_summary = section['text'][:500]  # First 500 chars as summary
            section_embedding = vector_store.get_embedding(section_summary)
            section_embeddings.append({
                'title': section['title'],
                'embedding': section_embedding
            })
        
        # Chunk-level embeddings
        chunk_texts = [chunk['text'] for chunk in doc_data['chunks']]
        chunk_embeddings = vector_store.get_embeddings_batch(chunk_texts)
        
        # Store in vector database
        logger.info("Storing in vector database...")
        await store_in_vector_db(doc_data, doc_embedding, section_embeddings, chunk_embeddings, metadata)
        
        # Store metadata in database
        logger.info("Storing metadata in database...")
        await store_metadata_in_db(doc_data)
        
        # Update document graph
        logger.info("Updating document graph...")
        await update_document_graph(doc_data, doc_embedding)
        
        logger.info(f"Successfully processed document: {original_filename}")

        # Upload document to Supabase storage
        logger.info(f"Uploading document to Supabase: {original_filename}")
        try:
            # Read the file content
            with open(file_path, 'rb') as f:
                file_content = f.read()

            # Determine content type based on file extension
            content_type_map = {
                'pdf': 'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'doc': 'application/msword',
                'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                'ppt': 'application/vnd.ms-powerpoint'
            }
            content_type = content_type_map.get(file_type, 'application/octet-stream')

            # Upload to 'documents' bucket with upsert option
            upload_result = supabase.storage.from_('documents').upload(
                path=original_filename,
                file=file_content,
                file_options={
                    "content-type": content_type,
                    "upsert": "true"  # Overwrite if exists
                }
            )

            # Get public URL
            file_url_result = supabase.storage.from_('documents').get_public_url(original_filename)
            file_url = file_url_result if isinstance(file_url_result, str) else file_url_result.get('publicUrl', '')

            logger.info(f"Document uploaded to Supabase: {file_url}")
        except Exception as e:
            logger.warning(f"Upload to Supabase failed (possibly duplicate), attempting to get existing file URL: {e}")
            # If upload fails, try to get URL of existing file
            try:
                file_url_result = supabase.storage.from_('documents').get_public_url(original_filename)
                file_url = file_url_result if isinstance(file_url_result, str) else file_url_result.get('publicUrl', '')
                logger.info(f"Using existing document URL: {file_url}")
            except Exception as url_error:
                logger.error(f"Failed to get file URL: {url_error}")
                file_url = None

        # Save metadata to database
        try:
            from ..models import DocumentMetadata
            session = db.get_session()
            if not session:
                logger.error("Cannot save metadata: Database session is None. Is DATABASE_URL configured?")
            if session:
                # Upsert document metadata
                doc_metadata = session.query(DocumentMetadata).filter_by(filename=original_filename).first()
                if doc_metadata:
                    # Update existing
                    doc_metadata.display_name = metadata.get('displayName', original_filename)
                    doc_metadata.document_type = metadata.get('documentType', 'article')
                    doc_metadata.document_source = metadata.get('documentSource', 'upload')
                    doc_metadata.human_capability_domain = metadata.get('humanCapabilityDomain', 'hr')
                    doc_metadata.author = metadata.get('author')
                    doc_metadata.publication_date = metadata.get('publicationDate')
                    doc_metadata.description = metadata.get('description')
                    doc_metadata.allow_download = metadata.get('allowDownload', True)
                    doc_metadata.show_in_viewer = metadata.get('showInViewer', True)
                else:
                    # Create new
                    doc_metadata = DocumentMetadata(
                        filename=original_filename,
                        display_name=metadata.get('displayName', original_filename),
                        document_type=metadata.get('documentType', 'article'),
                        document_source=metadata.get('documentSource', 'upload'),
                        human_capability_domain=metadata.get('humanCapabilityDomain', 'hr'),
                        author=metadata.get('author'),
                        publication_date=metadata.get('publicationDate'),
                        description=metadata.get('description'),
                        allow_download=metadata.get('allowDownload', True),
                        show_in_viewer=metadata.get('showInViewer', True),
                        bucket='documents'
                    )
                    session.add(doc_metadata)
                session.commit()
                logger.info(f"Saved metadata to database for {original_filename}")
                session.close()
        except Exception as e:
            logger.error(f"Error saving metadata to database: {e}")

    except Exception as e:
        logger.error(f"Error processing document {original_filename}: {e}")
        # Could update a status table here to mark as failed

async def process_video_task(file_path: str, file_type: str, original_filename: str, metadata: Dict[str, Any]):
    """Background task to process video - transcribe and index"""
    try:
        logger.info(f"Starting to process video: {original_filename}")

        # Initialize video processor and chunker
        video_processor = VideoProcessor()
        video_chunker = VideoChunker({
            'chunkSize': 1000,
            'chunkOverlap': 200,
            'minSegmentDuration': 10.0,
            'maxSegmentDuration': 120.0
        })

        # Read video file
        with open(file_path, 'rb') as f:
            video_content = f.read()

        logger.info(f"Transcribing video: {original_filename}")
        # Transcribe video using Whisper
        transcript_result = await video_processor.process_video(
            video_content=video_content,
            filename=original_filename
        )

        logger.info(f"Chunking transcript for: {original_filename}")
        # Chunk the transcript with timestamps
        base_metadata = {
            'filename': original_filename,
            'display_name': metadata.get('displayName', original_filename),
            'document_source': metadata.get('documentSource', 'upload'),
            'document_type': metadata.get('documentType', 'video'),
            'capability_domain': metadata.get('humanCapabilityDomain', 'hr'),
            'author': metadata.get('author', ''),
        }

        chunks = video_chunker.chunk_video_transcript(
            transcript_data=transcript_result['transcript'],
            metadata=base_metadata
        )

        logger.info(f"Created {len(chunks)} chunks for video: {original_filename}")

        # Upload video to Supabase storage
        logger.info(f"Uploading video to Supabase: {original_filename}")
        try:
            # Try to upload to 'documents' bucket with upsert option
            upload_result = supabase.storage.from_('documents').upload(
                path=original_filename,
                file=video_content,
                file_options={
                    "content-type": f"video/{file_type}",
                    "upsert": "true"  # Overwrite if exists
                }
            )

            # Get public URL
            file_url_result = supabase.storage.from_('documents').get_public_url(original_filename)
            file_url = file_url_result if isinstance(file_url_result, str) else file_url_result.get('publicUrl', '')

            logger.info(f"Video uploaded to Supabase: {file_url}")
        except Exception as e:
            logger.warning(f"Upload failed (possibly duplicate), attempting to get existing file URL: {e}")
            # If upload fails, try to get URL of existing file
            try:
                file_url_result = supabase.storage.from_('documents').get_public_url(original_filename)
                file_url = file_url_result if isinstance(file_url_result, str) else file_url_result.get('publicUrl', '')
                logger.info(f"Using existing video URL: {file_url}")
            except Exception as url_error:
                logger.error(f"Failed to get file URL: {url_error}")
                file_url = None

        # Generate embeddings and store in Pinecone
        logger.info(f"Generating embeddings for {len(chunks)} video chunks")
        chunks_indexed = 0

        for i, chunk in enumerate(chunks):
            try:
                chunk_id = f"video_{original_filename}_{i}"

                # Generate embedding for chunk content
                embedding = vector_store.get_embedding(chunk.content)

                # Prepare metadata for Pinecone
                pinecone_metadata = {
                    'content': chunk.content,
                    'filename': original_filename,
                    'title': metadata.get('displayName', original_filename),
                    'display_name': metadata.get('displayName', original_filename),
                    'section': metadata.get('documentSource', 'upload'),
                    'content_type': 'video',
                    'document_type': metadata.get('documentType', 'video'),
                    'capability_domain': metadata.get('humanCapabilityDomain', 'hr'),
                    'author': metadata.get('author', ''),
                    'start_time': chunk.start_time,
                    'end_time': chunk.end_time,
                    'duration': chunk.end_time - chunk.start_time,
                    'timestamp_display': chunk.metadata.get('timestamp_display', ''),
                    'language': chunk.metadata.get('language', 'en'),
                    'fileUrl': file_url or ''
                }

                # Store in Pinecone
                vector_store.index.upsert(
                    vectors=[(chunk_id, embedding, pinecone_metadata)]
                )

                chunks_indexed += 1

            except Exception as e:
                logger.error(f"Error indexing chunk {i} for video {original_filename}: {e}")
                continue

        logger.info(f"Successfully indexed {chunks_indexed}/{len(chunks)} chunks for video: {original_filename}")

        # Save metadata to database
        try:
            from ..models import DocumentMetadata
            session = db.get_session()
            if not session:
                logger.error("Cannot save metadata: Database session is None. Is DATABASE_URL configured?")
            if session:
                # Upsert document metadata
                doc_metadata = session.query(DocumentMetadata).filter_by(filename=original_filename).first()
                if doc_metadata:
                    # Update existing
                    doc_metadata.display_name = metadata.get('displayName', original_filename)
                    doc_metadata.document_type = metadata.get('documentType', 'video')
                    doc_metadata.document_source = metadata.get('documentSource', 'upload')
                    doc_metadata.human_capability_domain = metadata.get('humanCapabilityDomain', 'hr')
                    doc_metadata.author = metadata.get('author')
                    doc_metadata.publication_date = metadata.get('publicationDate')
                    doc_metadata.description = metadata.get('description')
                    doc_metadata.allow_download = metadata.get('allowDownload', True)
                    doc_metadata.show_in_viewer = metadata.get('showInViewer', True)
                else:
                    # Create new
                    doc_metadata = DocumentMetadata(
                        filename=original_filename,
                        display_name=metadata.get('displayName', original_filename),
                        document_type=metadata.get('documentType', 'video'),
                        document_source=metadata.get('documentSource', 'upload'),
                        human_capability_domain=metadata.get('humanCapabilityDomain', 'hr'),
                        author=metadata.get('author'),
                        publication_date=metadata.get('publicationDate'),
                        description=metadata.get('description'),
                        allow_download=metadata.get('allowDownload', True),
                        show_in_viewer=metadata.get('showInViewer', True),
                        bucket='documents'
                    )
                    session.add(doc_metadata)
                session.commit()
                logger.info(f"Saved metadata to database for {original_filename}")
                session.close()
        except Exception as e:
            logger.error(f"Error saving metadata to database: {e}")

        # Clean up temp file
        try:
            os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Could not delete temp file {file_path}: {e}")

    except Exception as e:
        logger.error(f"Error processing video {original_filename}: {e}")
        import traceback
        logger.error(traceback.format_exc())

async def store_in_vector_db(doc_data: Dict, doc_embedding: List[float],
                            section_embeddings: List[Dict], chunk_embeddings: List[List[float]],
                            metadata: Dict[str, Any] = None):
    """Store embeddings in Pinecone using namespaces"""

    if metadata is None:
        metadata = {}
    
    try:
        # Get the single index
        index = vector_store.index
        
        # Store document embedding in 'documents' namespace
        index.upsert(
            vectors=[{
                'id': doc_data['doc_id'],
                'values': doc_embedding,
                'metadata': {
                    'filename': doc_data.get('filename', doc_data.get('title', '')),
                    'title': doc_data['title'],
                    'summary': doc_data['summary'],
                    'concepts': ','.join(doc_data['concepts'][:10]),
                    'file_type': doc_data['file_type']
                }
            }],
            namespace='documents'
        )
        
        # Store section embeddings in 'sections' namespace
        section_vectors = []
        for i, section in enumerate(doc_data['sections']):
            section_vectors.append({
                'id': f"{doc_data['doc_id']}_section_{i}",
                'values': section_embeddings[i]['embedding'],
                'metadata': {
                    'filename': doc_data.get('filename', doc_data.get('title', '')),
                    'doc_id': doc_data['doc_id'],
                    'doc_title': doc_data['title'],
                    'section_title': section['title'],
                    'section_text': section['text'][:1000]
                }
            })
        
        if section_vectors:
            index.upsert(vectors=section_vectors, namespace='sections')
        
        # Store chunk embeddings in 'chunks' namespace
        chunk_vectors = []
        for i, chunk in enumerate(doc_data['chunks']):
            chunk_vectors.append({
                'id': f"{doc_data['doc_id']}_chunk_{i}",
                'values': chunk_embeddings[i],
                'metadata': {
                    'filename': doc_data.get('filename', doc_data.get('title', '')),
                    'doc_id': doc_data['doc_id'],
                    'doc_title': doc_data['title'],
                    'display_name': metadata.get('displayName', doc_data['title']),  # Add display name for UI
                    'section_title': chunk['section_title'],
                    'chunk_text': chunk['text'],
                    'chunk_id': chunk['chunk_id'],
                    'page_number': chunk.get('page_number')  # Include page number for PDF navigation
                }
            })
        
        if chunk_vectors:
            # Batch upsert in groups of 100
            batch_size = 100
            for i in range(0, len(chunk_vectors), batch_size):
                batch = chunk_vectors[i:i+batch_size]
                index.upsert(vectors=batch, namespace='chunks')
        
        logger.info(f"Stored {len(chunk_vectors)} chunks in vector database")
        
    except Exception as e:
        logger.error(f"Error storing in vector database: {e}")
        raise

async def store_metadata_in_db(doc_data: Dict):
    """Store document metadata in database"""
    
    try:
        if db.engine:
            # Store document metadata using SQLAlchemy
            from sqlalchemy import text
            
            with db.engine.connect() as conn:
                query = text("""
                    INSERT INTO documents (id, title, summary, concepts, file_type, file_path, 
                                         processed_at, num_sections, num_chunks)
                    VALUES (:id, :title, :summary, :concepts, :file_type, :file_path, 
                           :processed_at, :num_sections, :num_chunks)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        updated_at = NOW()
                """)
                
                conn.execute(query, {
                    'id': doc_data['doc_id'],
                    'title': doc_data['title'],
                    'summary': doc_data['summary'],
                    'concepts': json.dumps(doc_data['concepts']),
                    'file_type': doc_data['file_type'],
                    'file_path': doc_data['file_path'],
                    'processed_at': datetime.now(),
                    'num_sections': len(doc_data['sections']),
                    'num_chunks': len(doc_data['chunks'])
                })
                conn.commit()
                
            logger.info(f"Stored document metadata for: {doc_data['title']}")
        else:
            logger.warning("Database not connected, skipping metadata storage")
            
    except Exception as e:
        logger.error(f"Error storing metadata in database: {e}")
        # Continue processing even if metadata storage fails

async def update_document_graph(doc_data: Dict, doc_embedding: List[float]):
    """Update the document relationship graph"""
    
    try:
        if db.engine:
            # Get existing documents from database
            from sqlalchemy import text
            
            with db.engine.connect() as conn:
                result = conn.execute(text("SELECT * FROM documents"))
                existing_docs = [dict(row._mapping) for row in result]
            
            if existing_docs:
                # Get embeddings for existing documents
                embeddings = {doc_data['doc_id']: doc_embedding}
                
                # Fetch embeddings for other documents
                index = vector_store.index
                for doc in existing_docs:
                    if doc['id'] != doc_data['doc_id']:
                        try:
                            result = index.fetch(ids=[doc['id']], namespace='documents')
                            if doc['id'] in result['vectors']:
                                embeddings[doc['id']] = result['vectors'][doc['id']]['values']
                        except:
                            continue
                
                # Build updated graph
                all_docs = existing_docs + [doc_data]
                graph_builder.build_document_graph(all_docs, embeddings)
                
                logger.info("Document graph updated successfully")
        else:
            logger.warning("Database not connected, skipping graph update")
            
    except Exception as e:
        logger.error(f"Error updating document graph: {e}")

@router.get("/status/{doc_id}")
async def get_processing_status(doc_id: str):
    """Get processing status for a document"""
    
    try:
        if db.engine:
            from sqlalchemy import text
            
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("SELECT * FROM documents WHERE id = :id"),
                    {'id': doc_id}
                )
                row = result.first()
                
                if row:
                    return {
                        "status": "completed",
                        "document": dict(row._mapping)
                    }
        
        return {
            "status": "processing",
            "message": "Document is still being processed"
        }
            
    except Exception as e:
        logger.error(f"Error checking document status: {e}")
        raise HTTPException(status_code=500, detail="Error checking document status")

@router.get("/debug/metadata")
async def debug_metadata():
    """Debug endpoint to show all metadata in database"""
    try:
        from ..models import DocumentMetadata
        session = db.get_session()
        if not session:
            return {"error": "No database connection"}

        all_metadata = session.query(DocumentMetadata).all()
        result = []
        for meta in all_metadata:
            result.append({
                'filename': meta.filename,
                'display_name': meta.display_name,
                'document_type': meta.document_type,
                'document_source': meta.document_source,
                'author': meta.author,
                'human_capability_domain': meta.human_capability_domain,
                'publication_date': meta.publication_date,
                'description': meta.description
            })
        session.close()
        return {"count": len(result), "metadata": result}
    except Exception as e:
        return {"error": str(e)}

@router.get("/documents")
async def list_documents(page: int = 1, limit: int = 50):
    """List all uploaded documents from Supabase storage"""

    try:
        from ..core.database import supabase
        from ..models import DocumentMetadata

        all_files = []

        # Get metadata from database
        metadata_dict = {}
        session = db.get_session()
        if not session:
            logger.warning("Cannot load metadata: Database session is None. Is DATABASE_URL configured? Documents will show filename-based display.")
        if session:
            try:
                all_metadata = session.query(DocumentMetadata).all()
                metadata_dict = {meta.filename: meta for meta in all_metadata}
                logger.info(f"Loaded {len(metadata_dict)} document metadata records from database")
                session.close()
            except Exception as e:
                logger.error(f"Error loading metadata from database: {e}")
                if session:
                    session.close()

        # Check if Supabase storage is available
        if supabase:
            # List of buckets to check
            buckets = ['documents']

            for bucket_name in buckets:
                try:
                    logger.info(f"Fetching files from bucket: {bucket_name}")
                    files = supabase.storage.from_(bucket_name).list()

                    if files:
                        for file_obj in files:
                            # Add bucket info to each file object
                            file_obj['bucket'] = bucket_name
                            all_files.append(file_obj)
                        logger.info(f"Found {len(files)} files in {bucket_name}")
                    else:
                        logger.info(f"No files found in {bucket_name}")

                except Exception as e:
                    logger.error(f"Error listing files from bucket {bucket_name}: {e}")
                    continue

            if all_files:
                # Sort all files by created_at timestamp (newest first), handling None values
                sorted_files = sorted(all_files, key=lambda x: x.get('created_at') or '1970-01-01', reverse=True)
                total_count = len(sorted_files)

                # Paginate results
                start_idx = (page - 1) * limit
                end_idx = start_idx + limit
                paginated_files = sorted_files[start_idx:end_idx]

                documents = []
                for file_obj in paginated_files:
                    file_name = file_obj['name']
                    bucket_name = file_obj.get('bucket', 'documents')

                    # Check if we have metadata from database
                    db_metadata = metadata_dict.get(file_name)

                    # Debug logging for filename matching
                    if not db_metadata and file_name.endswith(('.mp4', '.webm', '.mov', '.avi')):
                        logger.warning(f"No metadata found for video: '{file_name}'. Available keys: {list(metadata_dict.keys())}")

                    if db_metadata:
                        # Use metadata from database
                        display_name = db_metadata.display_name
                        doc_type = db_metadata.document_type
                        source = db_metadata.document_source
                        author = db_metadata.author or 'Unknown'
                        publication_date = db_metadata.publication_date or (file_obj.get('created_at') or datetime.now().isoformat())[:10]
                        description = db_metadata.description or ''
                        allow_download = db_metadata.allow_download
                        show_in_viewer = db_metadata.show_in_viewer
                    else:
                        # Fallback to filename-based logic for documents without metadata
                        clean_name = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name

                        # Remove timestamp patterns: YYYYMMDD_HHMMSS_ or TIMESTAMP_
                        if '_' in clean_name:
                            parts = clean_name.split('_')
                            # Remove leading numeric parts (timestamps)
                            while parts and parts[0].replace('.', '').replace('-', '').isdigit():
                                parts.pop(0)
                            clean_name = '_'.join(parts) if parts else clean_name

                        # Add spaces before capital letters (camelCase to Title Case)
                        clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_name)
                        # Replace underscores and hyphens with spaces
                        clean_name = clean_name.replace('_', ' ').replace('-', ' ')
                        # Clean up multiple spaces
                        clean_name = re.sub(r'\s+', ' ', clean_name).strip()

                        display_name = clean_name or file_name
                        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
                        doc_type = 'video' if file_ext in ['mp4', 'webm', 'mov', 'avi'] else 'article'
                        source = 'upload'
                        author = 'Unknown'
                        publication_date = (file_obj.get('created_at') or datetime.now().isoformat())[:10]
                        description = ''
                        allow_download = True
                        show_in_viewer = True

                    documents.append({
                        'id': f"{bucket_name}_{file_name.rsplit('.', 1)[0]}",
                        'displayName': display_name,
                        'filename': file_name,
                        'documentSource': source,
                        'documentType': doc_type,
                        'humanCapabilityDomain': db_metadata.human_capability_domain if db_metadata else 'hr',
                        'author': author,
                        'publicationDate': publication_date,
                        'uploadDate': file_obj.get('updated_at') or file_obj.get('created_at') or datetime.now().isoformat(),
                        'description': description,
                        'allowDownload': allow_download,
                        'showInViewer': show_in_viewer,
                        'size': (file_obj.get('metadata') or {}).get('size', 0),
                        'permissions': 'read',
                        'fileUrl': f'/api/documents/{file_name}?bucket={bucket_name}',
                        'bucket': bucket_name
                    })
            else:
                total_count = 0
                documents = []
        else:
            logger.warning("Supabase storage not available")
            total_count = 0
            documents = []

        return {
            'documents': documents,
            'total': total_count,
            'page': page,
            'limit': limit,
            'pages': (total_count + limit - 1) // limit if total_count > 0 else 0
        }

    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing documents: {str(e)}")

@router.post("/bulk-upload")
async def bulk_upload_documents(
    files: List[UploadFile] = File(...),
    metadata_list: str = Form(None),
    chunking_config: str = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Upload multiple documents at once with per-file metadata"""

    # Parse metadata list - a JSON array where each item corresponds to a file
    try:
        file_metadata_list = json.loads(metadata_list) if metadata_list else []
    except json.JSONDecodeError:
        file_metadata_list = []

    # Parse chunking config (same for all files)
    try:
        chunking_config_dict = json.loads(chunking_config) if chunking_config else {}
    except json.JSONDecodeError:
        chunking_config_dict = {}

    results = []

    for i, file in enumerate(files):
        # Validate file type
        file_ext = file.filename.split('.')[-1].lower()
        allowed_types = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'mp4', 'webm', 'mov', 'avi', 'mkv']

        if file_ext not in allowed_types:
            results.append({
                "filename": file.filename,
                "status": "rejected",
                "reason": f"Unsupported file type: .{file_ext}"
            })
            continue

        # Get metadata for this file (by index or by filename match)
        file_metadata = {}
        if i < len(file_metadata_list):
            file_metadata = file_metadata_list[i]
        else:
            # Try to find by filename
            for meta in file_metadata_list:
                if meta.get('filename') == file.filename:
                    file_metadata = meta
                    break

        # Save file
        file_path = UPLOAD_DIR / f"{datetime.now().timestamp()}_{file.filename}"

        try:
            with file_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Determine if video
            video_extensions = ['mp4', 'webm', 'mov', 'avi', 'mkv']
            is_video = file_ext in video_extensions

            # Add to background processing with metadata
            if is_video:
                background_tasks.add_task(process_video_task, str(file_path), file_ext, file.filename, file_metadata)
            else:
                background_tasks.add_task(process_document_task, str(file_path), file_ext, file.filename, file_metadata, chunking_config_dict)

            results.append({
                "filename": file.filename,
                "status": "queued"
            })

        except Exception as e:
            logger.error(f"Error processing {file.filename}: {e}")
            results.append({
                "filename": file.filename,
                "status": "error",
                "reason": str(e)
            })

    return {
        "message": f"Processing {len(files)} documents",
        "results": results
    }

@router.delete("/documents/{filename}")
async def delete_document(filename: str, bucket: str = "documents"):
    """Delete a document from Supabase storage, metadata table, and Pinecone vector database"""

    try:
        from ..core.database import supabase, db
        from ..models.document import DocumentMetadata

        if not supabase:
            raise HTTPException(status_code=503, detail="Storage service is not available")

        deleted_from = []
        errors = []

        # 1. Delete from Supabase storage
        try:
            supabase.storage.from_(bucket).remove([filename])
            deleted_from.append("storage")
            logger.info(f"Deleted {filename} from Supabase storage")
        except Exception as e:
            logger.error(f"Error deleting file from storage: {e}")
            errors.append(f"storage: {str(e)}")

        # 2. Delete from document_metadata table (Supabase/PostgreSQL)
        try:
            session = db.get_session()
            if session:
                # Find and delete the document metadata record
                doc = session.query(DocumentMetadata).filter(
                    DocumentMetadata.filename == filename
                ).first()
                if doc:
                    session.delete(doc)
                    session.commit()
                    deleted_from.append("metadata")
                    logger.info(f"Deleted metadata for {filename} from document_metadata table")
                else:
                    logger.warning(f"No metadata record found for {filename}")
                session.close()
        except Exception as e:
            logger.error(f"Error deleting from metadata table: {e}")
            errors.append(f"metadata: {str(e)}")

        # 3. Delete from Pinecone vector database (all namespaces)
        try:
            result = vector_store.delete_by_filename(filename)
            deleted_from.append("pinecone")
            logger.info(f"Deleted vectors for {filename} from Pinecone: {result}")
        except Exception as e:
            logger.warning(f"Could not delete from Pinecone: {e}")
            errors.append(f"pinecone: {str(e)}")

        # Return success if at least storage was deleted
        if "storage" in deleted_from or "metadata" in deleted_from:
            return {
                "message": f"Successfully deleted {filename}",
                "filename": filename,
                "bucket": bucket,
                "deleted_from": deleted_from,
                "errors": errors if errors else None
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete document from any location. Errors: {errors}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting document: {str(e)}")

@router.get("/documents/{filename}/download")
async def download_document(filename: str, bucket: str = "documents"):
    """Generate a signed URL for downloading a document from Supabase storage"""

    try:
        from ..core.database import supabase

        if not supabase:
            raise HTTPException(status_code=503, detail="Storage service is not available")

        # Generate a signed URL (valid for 1 hour)
        signed_url = supabase.storage.from_(bucket).create_signed_url(
            filename,
            3600  # 1 hour expiry
        )

        if not signed_url or 'signedURL' not in signed_url:
            raise HTTPException(status_code=404, detail=f"Could not generate download URL for {filename}")

        return {
            "url": signed_url['signedURL'],
            "filename": filename,
            "bucket": bucket,
            "expires_in": 3600
        }

    except Exception as e:
        logger.error(f"Error generating download URL for {filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating download URL: {str(e)}")


# ============== System Prompt Configuration ==============

@router.get("/system-prompt")
async def get_system_prompt():
    """Get the current system prompt configuration"""
    try:
        from ..config.system_prompt import get_system_prompt, get_default_prompt

        current_prompt = get_system_prompt()
        default_prompt = get_default_prompt()
        is_custom = current_prompt != default_prompt

        return {
            "prompt": current_prompt,
            "is_custom": is_custom,
            "default_prompt": default_prompt
        }
    except Exception as e:
        logger.error(f"Error getting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting system prompt: {str(e)}")


@router.put("/system-prompt")
async def update_system_prompt(data: dict):
    """Update the system prompt"""
    try:
        from ..config.system_prompt import set_system_prompt

        prompt = data.get('prompt', '')

        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="Prompt cannot be empty")

        success = set_system_prompt(prompt)

        if success:
            return {"message": "System prompt updated successfully", "success": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to save system prompt")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating system prompt: {str(e)}")


@router.post("/system-prompt/reset")
async def reset_system_prompt():
    """Reset system prompt to default"""
    try:
        from ..config.system_prompt import reset_system_prompt, get_default_prompt

        success = reset_system_prompt()

        if success:
            return {
                "message": "System prompt reset to default",
                "success": True,
                "prompt": get_default_prompt()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reset system prompt")

    except Exception as e:
        logger.error(f"Error resetting system prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting system prompt: {str(e)}")