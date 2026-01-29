#!/usr/bin/env python3
"""
Reindex all documents in Pinecone to add page numbers
"""
import sys
import os
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import db, supabase
from app.core.vector_store import vector_store
from app.models import DocumentMetadata
from app.processing.document_processor import DocumentProcessor
import logging
import tempfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reindex_all_documents():
    """Reindex all documents with proper chunking configuration"""

    logger.info("Starting document reindexing with 3000-character chunks...")

    # Get all documents from database
    session = db.get_session()
    if not session:
        logger.error("Cannot connect to database")
        return

    documents = session.query(DocumentMetadata).all()
    logger.info(f"Found {len(documents)} documents in database")

    # Create processor with 3000 character chunks, 200 character overlap, and list preservation
    processor = DocumentProcessor(chunk_size=3000, chunk_overlap=200, preserve_lists=True)
    logger.info("Using chunking config: 3000 chars with 200 char overlap, preserving lists")

    for doc_metadata in documents:
        filename = doc_metadata.filename
        logger.info(f"\n{'='*60}")
        logger.info(f"Reindexing: {filename}")

        try:
            # Download from Supabase
            logger.info(f"  Downloading from Supabase...")
            file_data = supabase.storage.from_('documents').download(filename)

            if not file_data:
                logger.error(f"  Failed to download {filename}")
                continue

            # Save to temp file
            file_ext = filename.split('.')[-1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}') as tmp_file:
                tmp_file.write(file_data)
                tmp_path = tmp_file.name

            logger.info(f"  Processing document...")
            # Process document (this extracts page numbers)
            doc_data = await processor.process_document(tmp_path, file_ext)
            doc_data['title'] = filename
            doc_data['filename'] = filename

            logger.info(f"  Generated {len(doc_data['chunks'])} chunks")

            # Generate embeddings
            logger.info(f"  Generating embeddings...")

            # Document-level embedding
            doc_embedding = vector_store.get_embedding(doc_data['summary'])

            # Section-level embeddings
            section_embeddings = []
            for section in doc_data['sections']:
                section_summary = section['text'][:500]
                section_embedding = vector_store.get_embedding(section_summary)
                section_embeddings.append({
                    'title': section['title'],
                    'embedding': section_embedding
                })

            # Chunk-level embeddings
            chunk_texts = [chunk['text'] for chunk in doc_data['chunks']]
            chunk_embeddings = vector_store.get_embeddings_batch(chunk_texts)

            # Store in Pinecone
            logger.info(f"  Storing in Pinecone...")
            index = vector_store.index

            # Store document embedding in 'documents' namespace
            doc_vector = {
                'id': doc_data['doc_id'],
                'values': doc_embedding,
                'metadata': {
                    'filename': filename,
                    'title': doc_data['title'],
                    'summary': doc_data['summary'][:1000],
                    'concepts': doc_data['concepts'][:500],
                    'file_type': file_ext
                }
            }
            index.upsert(vectors=[doc_vector], namespace='documents')

            # Store section embeddings in 'sections' namespace
            section_vectors = []
            for i, section in enumerate(doc_data['sections']):
                section_vectors.append({
                    'id': f"{doc_data['doc_id']}_section_{i}",
                    'values': section_embeddings[i]['embedding'],
                    'metadata': {
                        'filename': filename,
                        'doc_id': doc_data['doc_id'],
                        'doc_title': doc_data['title'],
                        'section_title': section['title'],
                        'section_text': section['text'][:1000]
                    }
                })

            if section_vectors:
                index.upsert(vectors=section_vectors, namespace='sections')

            # Store chunk embeddings in 'chunks' namespace WITH PAGE NUMBERS AND DISPLAY NAME
            chunk_vectors = []
            for i, chunk in enumerate(doc_data['chunks']):
                chunk_vectors.append({
                    'id': f"{doc_data['doc_id']}_chunk_{i}",
                    'values': chunk_embeddings[i],
                    'metadata': {
                        'filename': filename,
                        'doc_id': doc_data['doc_id'],
                        'doc_title': doc_data['title'],
                        'display_name': doc_metadata.display_name,  # Add display name for UI
                        'section_title': chunk['section_title'],
                        'chunk_text': chunk['text'],
                        'chunk_id': chunk['chunk_id'],
                        'page_number': chunk.get('page_number')  # Include page numbers
                    }
                })

            if chunk_vectors:
                # Batch upsert in groups of 100
                batch_size = 100
                for i in range(0, len(chunk_vectors), batch_size):
                    batch = chunk_vectors[i:i+batch_size]
                    index.upsert(vectors=batch, namespace='chunks')

            logger.info(f"  ✅ Successfully reindexed {filename}")
            logger.info(f"     Chunks with page numbers: {sum(1 for c in doc_data['chunks'] if c.get('page_number'))}")

            # Clean up temp file
            os.unlink(tmp_path)

        except Exception as e:
            logger.error(f"  ❌ Error reindexing {filename}: {e}", exc_info=True)
            continue

    session.close()
    logger.info(f"\n{'='*60}")
    logger.info("✅ Reindexing complete!")

if __name__ == "__main__":
    print("\n🔄 DOCUMENT REINDEXING")
    print("="*60)
    print("This will reprocess all documents to add page numbers.")
    print("Existing vectors will be replaced with updated versions.")
    print("="*60)

    response = input("\nContinue? (yes/no): ")
    if response.lower() == 'yes':
        asyncio.run(reindex_all_documents())
    else:
        print("Cancelled.")
