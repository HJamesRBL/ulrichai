# backend/app/services/chat_service.py

from typing import List, Dict, Any, Optional
import openai
from dotenv import load_dotenv
import os
import logging
import json
from datetime import datetime
import re

from ..core.vector_store import vector_store
from ..core.database import db

load_dotenv()

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

logger = logging.getLogger(__name__)

class DocumentNameMapper:
    """
    Helper class for mapping file names to display names.
    """
    
    @classmethod
    def get_display_name(cls, filename: str) -> str:
        """Get a clean display name for a document."""
        if not filename:
            return "Unknown Document"
        
        # Remove timestamp prefix if present (format: YYYYMMDD_HHMMSS_)
        if re.match(r'^\d{8}_\d{6}_', filename):
            filename = re.sub(r'^\d{8}_\d{6}_', '', filename)
        
        # Remove extension
        name = filename.rsplit('.', 1)[0]
        
        # Replace underscores and hyphens with spaces
        name = name.replace('_', ' ').replace('-', ' ')
        
        # Handle CamelCase
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        
        # Capitalize words
        name = ' '.join(word.capitalize() for word in name.split())
        
        # Handle common abbreviations
        abbreviations = {
            'Hr': 'HR', 'Ai': 'AI', 'Ml': 'ML', 'Rbl': 'RBL',
            'Kpi': 'KPI', 'Roi': 'ROI', 'Ceo': 'CEO', 'Cfo': 'CFO',
            'Cto': 'CTO', 'Vp': 'VP', 'Svp': 'SVP', 'Evp': 'EVP'
        }
        
        for abbr, replacement in abbreviations.items():
            name = name.replace(abbr, replacement)
        
        return name

class ChatService:
    def _format_document_source(self, source: str) -> str:
        """Convert technical document source to user-friendly display name"""
        if not source:
            return "Main Content"
        
        # Define mappings for common sources
        source_mappings = {
            'dave-ulrich-hr-academy': 'Dave Ulrich HR Academy',
            'institute': 'RBL Institute',
            'rbl-institute': 'RBL Institute',
            'external': 'External Source',
            'case-study': 'Case Study',
            'white-paper': 'White Paper',
            'research': 'Research',
            'blog': 'Blog',
            'article': 'Article',
            'playbook': 'Playbook',
            'toolkit': 'Toolkit'
        }
        
        # Check for exact match first
        if source.lower() in source_mappings:
            return source_mappings[source.lower()]
        
        # If no exact match, format the string nicely
        # Replace hyphens and underscores with spaces, then title case
        formatted = source.replace('-', ' ').replace('_', ' ')
        return ' '.join(word.capitalize() for word in formatted.split())

    def __init__(self):
        self.max_context_docs = 5
        self.max_context_chunks = 10
        self.name_mapper = DocumentNameMapper()

    def detect_query_intent(self, query: str) -> str:
        """Detect whether user wants teaching/explanation or resource discovery.

        Returns:
            "assist" - User wants to find resources/documents
            "teach" - User wants explanation/understanding (default)
        """
        query_lower = query.lower()

        # Keywords that strongly indicate resource discovery intent
        assist_keywords = [
            "find", "show me", "give me",
            "resources on", "resources about", "resources for",
            "documents on", "documents about", "documents for",
            "materials on", "materials about", "materials for",
            "papers on", "papers about",
            "readings on", "readings about",
            "sources on", "sources about",
            "where can i find", "where can i read",
            "point me to", "direct me to",
            "list of resources", "list of documents"
        ]

        # Check for assist keywords
        for keyword in assist_keywords:
            if keyword in query_lower:
                logger.info(f"Detected ASSIST intent (keyword: '{keyword}')")
                return "assist"

        # Default to teach mode
        logger.info("Detected TEACH intent (default)")
        return "teach"

    async def process_query(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Process a user query using Sandusky Current's approach"""
        
        try:
            logger.info(f"Processing query: {query}")
            
            # Search for context (like Sandusky) - increased to get more comprehensive results
            search_results = await self.search_context(query, limit=10)
            
            # Build context prompt (like Sandusky)
            context_prompt = self.build_context_prompt(search_results)
            
            # Create the full prompt for OpenAI
            full_prompt = f"""Based on the following context, please provide a comprehensive answer about HR and organizational development.

{context_prompt}

Question: {query}

IMPORTANT INSTRUCTIONS:
1. Present information with the authoritative confidence of Dave Ulrich's decades of organizational research
2. Extract frameworks, dimensions, and lists exactly as they appear in the source materials
3. Use Dave Ulrich's direct, business-focused communication style - no hedging or tentative language
4. Structure responses with clear frameworks and practical applications
5. Focus on actionable insights that drive organizational effectiveness
6. Avoid phrases like "However, this may not be complete" or "additional factors may exist"

Provide a comprehensive, authoritative response in Dave Ulrich's voice based on the context above."""
            
            # Generate response using OpenAI
            response = await self.generate_response(full_prompt)
            
            # Format sources for frontend
            sources = []
            for doc in search_results.get('documents', [])[:4]:  # Limit to 4 like original
                raw_section = doc.get('section', '')
                formatted_section = self._format_document_source(raw_section)
                
                sources.append({
                    "title": doc.get('title', ''),
                    "filename": doc.get('filename', ''),
                    "content": doc.get('content', '')[:200],  # Preview
                    "score": doc.get('score', 0.0),
                    "page_number": doc.get('page_number'),
                    "section": formatted_section,
                    "type": "chunk",
                    "start_time": doc.get('start_time'),
                    "end_time": doc.get('end_time')
                })
            
            formatted_response = {
                "answer": response,
                "sources": sources,
                "timestamp": datetime.now().isoformat()
            }
            
            # Log analytics
            await self.log_analytics(query, formatted_response, session_id)
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "I apologize, but I encountered an error processing your question. Please try again.",
                "sources": [],
                "error": str(e)
            }
    
    async def search_context(self, query: str, limit: int = 5, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Enhanced search with sequential chunk retrieval for structured content and optional lesson/course filtering"""

        logger.info(f"Searching context for query: {query}")
        if context:
            logger.info(f"Context provided: {context}")

        try:
            # Generate query embedding using OpenAI
            embedding_response = openai.embeddings.create(
                model="text-embedding-3-large",
                input=query,
                dimensions=1024
            )
            query_embedding = embedding_response.data[0].embedding
            logger.info(f"Generated embedding with {len(query_embedding)} dimensions")

            # Search documents using Pinecone
            index = vector_store.index

            # Debug: Log index stats
            index_stats = index.describe_index_stats()
            logger.info(f"Index stats: {index_stats}")

            # Build filter for lesson/course context if provided
            metadata_filter = None
            if context and context.get('type') == 'lesson':
                # Filter by course_id to get all content from the current course
                # This prioritizes course-specific content while still allowing general knowledge
                if context.get('course_id'):
                    metadata_filter = {
                        "course_id": {"$eq": context.get('course_id')}
                    }
                    logger.info(f"Filtering by course_id: {context.get('course_id')}")

            # Search only document-level embeddings for document discovery mode
            all_matches = []
            namespaces_to_search = ['documents']  # Document-level search only

            for ns in namespaces_to_search:
                try:
                    ns_results = index.query(
                        vector=query_embedding,
                        top_k=limit * 2 if metadata_filter else limit,  # Get more results when filtering
                        include_metadata=True,
                        filter=metadata_filter,
                        namespace=ns
                    )
                    if ns_results.matches:
                        all_matches.extend(ns_results.matches)
                        logger.info(f"Namespace '{ns}': found {len(ns_results.matches)} matches")
                except Exception as e:
                    logger.warning(f"Error searching namespace '{ns}': {e}")

            # Sort all matches by score (descending) and take top K
            all_matches.sort(key=lambda m: m.score, reverse=True)
            search_results = type('obj', (object,), {'matches': all_matches[:limit * 2 if metadata_filter else limit]})()

            # Debug: Log what we got back from search
            logger.info(f"Search returned {len(search_results.matches)} matches (across all namespaces)")
            for i, match in enumerate(search_results.matches[:2]):  # Log first 2 matches
                logger.info(f"Match {i}: score={match.score}, metadata keys: {match.metadata.keys()}")
                if match.metadata.get('content_type') == 'video':
                    logger.info(f"Video match - start_time: {match.metadata.get('start_time')}, end_time: {match.metadata.get('end_time')}")
            
            # Debug: Log search results
            logger.info(f"Raw search results: {len(search_results.matches) if search_results.matches else 0} matches")
            
            # Format results and detect if this is a structured query
            documents = []
            if search_results.matches:
                # Check if this appears to be asking for structured content
                is_structured_query = self._is_structured_query(query)
                
                for match in search_results.matches:
                    # Document-level metadata from 'documents' namespace
                    # Contains: title, summary, concepts, file_type
                    title = match.metadata.get('title', '')
                    summary = match.metadata.get('summary', '')
                    concepts = match.metadata.get('concepts', '')
                    file_type = match.metadata.get('file_type', '')

                    # For document discovery, use summary as the content
                    content = summary if summary else match.metadata.get('content') or match.metadata.get('chunk_text', '')

                    # Extract display_name (user-friendly name) or generate from title
                    display_name = match.metadata.get('display_name')
                    if not display_name:
                        display_name = self.name_mapper.get_display_name(title)

                    # Use title as filename for documents namespace
                    filename = match.metadata.get('filename', '') or title

                    documents.append({
                        'content': content,
                        'summary': summary,  # Full document summary
                        'concepts': concepts,  # Document concepts/keywords
                        'title': title,
                        'display_name': display_name,
                        'filename': filename,
                        'file_type': file_type,
                        'score': float(match.score) if hasattr(match, 'score') else 0.0,
                        'document_id': match.id if hasattr(match, 'id') else None,
                        'content_type': 'document'  # Mark as document-level result
                    })
                
                # Filter out AI training documents (documents that shouldn't appear in RAG results)
                documents = await self._filter_allowed_documents(documents)

                # If structured query, get sequential chunks from best matches
                if is_structured_query and documents:
                    logger.info("Detected structured query - fetching sequential chunks")
                    documents = await self._get_sequential_chunks(documents, index)

            logger.info(f"Found {len(documents)} relevant documents (including sequential chunks)")

            return {
                'documents': documents
            }
            
        except Exception as e:
            logger.error(f"Error in search_context: {e}")
            return {'documents': []}
    
    def build_context_prompt(self, search_results: Dict[str, Any]) -> str:
        """Build context prompt using Sandusky Current's approach"""

        context_parts = []

        # Add relevant documents
        documents = search_results.get('documents', [])
        if documents:
            context_parts.append("**RELEVANT DOCUMENTS:**")
            for doc in documents:
                # Support multiple metadata formats (old and new)
                title = doc.get('title') or doc.get('doc_title', 'Unknown Document')
                content = doc.get('content') or doc.get('chunk_text', '')
                content = content[:800] if content else ''  # Increased from 500 for better context
                page_num = doc.get('page_number', '')
                start_time = doc.get('start_time')
                end_time = doc.get('end_time')
                content_type = doc.get('content_type')

                doc_info = f"- **{title}**"

                # Add location info (page number for PDFs, timestamp for videos)
                if content_type == 'lesson_video' and start_time is not None:
                    # Convert seconds to MM:SS format
                    minutes = int(start_time // 60)
                    seconds = int(start_time % 60)
                    timestamp = f"{minutes:02d}:{seconds:02d}"
                    doc_info += f" (Video timestamp: {timestamp})"
                elif page_num:
                    doc_info += f" (Page {page_num})"

                doc_info += f": {content}"

                context_parts.append(doc_info)

            context_parts.append("")  # Add spacing

        return "\n".join(context_parts) if context_parts else ""

    def build_context_prompt_assistant_mode(self, search_results: Dict[str, Any]) -> str:
        """Build context prompt for assistant mode - groups by document and shows page ranges"""

        documents = search_results.get('documents', [])
        if not documents:
            return ""

        # Group documents by filename (or doc_id)
        doc_groups = {}
        for doc in documents:
            filename = doc.get('filename', 'Unknown')
            if filename not in doc_groups:
                # Get display name - try metadata first, then generate from filename
                display_name = doc.get('display_name')
                if not display_name or display_name == filename:
                    # Generate a clean display name from the filename
                    display_name = self.name_mapper.get_display_name(filename)

                doc_groups[filename] = {
                    'display_name': display_name,
                    'pages': set(),
                    'chunks': [],
                    'content_type': doc.get('content_type')
                }

            # Add page number if present
            page_num = doc.get('page_number')
            if page_num:
                doc_groups[filename]['pages'].add(page_num)

            # Add chunk with its score for sorting
            doc_groups[filename]['chunks'].append({
                'content': doc.get('content', ''),
                'score': doc.get('score', 0.0),
                'start_time': doc.get('start_time'),
                'end_time': doc.get('end_time')
            })

        # Build formatted context
        context_parts = ["**RELEVANT RESOURCES:**"]

        # Limit to top 4-5 documents
        sorted_docs = sorted(doc_groups.items(),
                           key=lambda x: max(c['score'] for c in x[1]['chunks']),
                           reverse=True)[:5]

        logger.info(f"Building assistant context for {len(sorted_docs)} documents from {len(doc_groups)} groups")

        for filename, doc_info in sorted_docs:
            display_name = doc_info['display_name']
            content_type = doc_info['content_type']

            # Format location info
            location_info = ""
            if content_type == 'lesson_video' and doc_info['chunks']:
                # For videos, show timestamp range
                start_times = [c['start_time'] for c in doc_info['chunks'] if c.get('start_time') is not None]
                if start_times:
                    min_time = min(start_times)
                    minutes = int(min_time // 60)
                    seconds = int(min_time % 60)
                    location_info = f" (Video timestamp: {minutes:02d}:{seconds:02d})"
            elif doc_info['pages']:
                # For PDFs, show page range
                sorted_pages = sorted(doc_info['pages'])
                if len(sorted_pages) == 1:
                    location_info = f" (Page {sorted_pages[0]})"
                else:
                    # Format page ranges nicely
                    page_str = ", ".join(str(p) for p in sorted_pages)
                    location_info = f" (Pages {page_str})"

            # Build the document entry WITHOUT revealing the filename
            doc_header = f"- **{display_name}**{location_info}"
            context_parts.append(doc_header)
            logger.info(f"Added to context: {doc_header}")

            # Sort chunks by score and take top 2-3 for this document
            sorted_chunks = sorted(doc_info['chunks'], key=lambda x: x['score'], reverse=True)[:3]

            # Combine excerpts (limit total to ~1200 chars per document)
            excerpts = []
            total_chars = 0
            for chunk in sorted_chunks:
                content = chunk['content']
                if content:
                    # Limit each excerpt to 400 chars
                    excerpt = content[:400] if len(content) > 400 else content
                    if total_chars + len(excerpt) <= 1200:
                        excerpts.append(excerpt)
                        total_chars += len(excerpt)

            # Join excerpts with separator
            combined_excerpt = " ... ".join(excerpts)
            context_parts.append(f"  {combined_excerpt}")
            context_parts.append("")  # Add spacing between documents

        return "\n".join(context_parts)

    async def get_graph_context(self, doc_id: str) -> List[str]:
        """Get related documents from the graph"""
        
        try:
            from ..processing.graph_builder import graph_builder
            
            # Get related documents
            related = graph_builder.find_related_documents(doc_id, max_docs=3)
            
            # Fetch their summaries
            related_summaries = []
            if related and db.engine:
                from sqlalchemy import text
                
                with db.engine.connect() as conn:
                    for rel_doc_id, weight in related:
                        result = conn.execute(
                            text("SELECT display_name, description FROM admin_documents WHERE id = :id"),
                            {'id': rel_doc_id}
                        )
                        row = result.first()
                        if row:
                            related_summaries.append({
                                'title': row.display_name,
                                'summary': row.description[:200] if row.description else '',
                                'relevance': weight
                            })
            
            return related_summaries
            
        except Exception as e:
            logger.error(f"Error getting graph context: {e}")
            return []
    
    
    async def get_sources_for_query(self, query: str) -> List[Dict[str, Any]]:
        """Get document-level sources for discovery mode - returns documents with summaries"""
        try:
            search_results = await self.search_context(query, limit=10)
            documents = search_results.get('documents', [])
            logger.info(f"📋 get_sources_for_query: Received {len(documents)} document-level results")

            # Document discovery mode: Return document-level results with summaries
            # Each document from 'documents' namespace is already unique
            sources = []
            for doc in documents[:10]:  # Limit to top 10 documents
                display_name = doc.get('display_name')
                if not display_name:
                    display_name = self.name_mapper.get_display_name(doc.get('filename', doc.get('title', '')))

                sources.append({
                    "title": display_name,
                    "filename": doc.get('filename', ''),
                    "content": doc.get('summary', doc.get('content', '')),  # Use full summary
                    "summary": doc.get('summary', ''),  # Explicit summary field
                    "concepts": doc.get('concepts', ''),  # Document concepts/keywords
                    "score": doc.get('score', 0.0),
                    "file_type": doc.get('file_type', ''),
                    "type": "document",  # Mark as document-level result
                    "document_id": doc.get('document_id')
                })

            logger.info(f"📋 Returning {len(sources)} document sources with summaries")
            return sources

        except Exception as e:
            logger.error(f"❌ Error getting sources: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    async def process_query_stream(self, query: str, session_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None):
        """Process query with streaming response, optionally with lesson context"""
        try:
            logger.info(f"Processing streaming query: {query[:200]}...")

            # Check if this is a lesson context query
            if context and context.get('type') == 'lesson':
                # Extract the actual user question from the frontend's context prompt
                user_question = query
                if "**Student's Question:**" in query:
                    # Extract just the question for better semantic search
                    parts = query.split("**Student's Question:**")
                    if len(parts) > 1:
                        user_question = parts[1].split('\n')[0].strip()
                        logger.info(f"Extracted user question: {user_question}")

                # Search using just the user's question for better semantic matching
                search_results = await self.search_context(user_question, limit=10, context=context)
                context_prompt = self.build_context_prompt(search_results)

                # Replace the placeholder context in the full prompt with RAG context
                # Insert our RAG context before the student's question
                if "**Student's Question:**" in query:
                    parts = query.split("**Student's Question:**")
                    full_prompt = f"""{parts[0]}
{context_prompt}

**Student's Question:** {parts[1]}"""
                else:
                    # Fallback if format doesn't match
                    full_prompt = f"{query}\n\n{context_prompt}"
            else:
                # Normal query - search for context without filtering
                search_results = await self.search_context(query, limit=10)

                # Detect intent: teach or assist
                intent = self.detect_query_intent(query)

                # Build context based on intent
                if intent == "assist":
                    # Use assistant-mode context builder (groups by document)
                    context_prompt = self.build_context_prompt_assistant_mode(search_results)
                    logger.info(f"Assistant mode context (first 500 chars): {context_prompt[:500]}")
                else:
                    # Use regular context builder (shows all chunks separately)
                    context_prompt = self.build_context_prompt(search_results)
                    logger.info(f"Teacher mode context (first 500 chars): {context_prompt[:500]}")

                # Create the full prompt based on intent
                if intent == "assist":
                    # Assistant mode: Focus on presenting resources
                    full_prompt = f"""Based on the following context, help the user discover relevant resources.

{context_prompt}

Question: {query}

IMPORTANT INSTRUCTIONS (ASSISTANT MODE):
1. Provide a brief 1-2 sentence introduction explaining why these resources address the query

2. List UNIQUE documents only - ONE entry per document:
   - Copy the **EXACT Display Name** as it appears in bold in the context (e.g., "What Makes an Effective HR Function?" NOT "February 2023 Playbook_final.pdf")
   - Copy the page numbers or timestamp EXACTLY as shown in parentheses after the display name
   - Include a 2-3 sentence summary of what the document covers

3. CRITICAL RULES:
   - NEVER invent or use filenames (like "Something.pdf") - ONLY use the display names shown in **bold**
   - If a document shows "(Pages 19, 24, 25)", list it ONCE with those exact pages, NOT as separate entries
   - List exactly the documents shown in the context, no more, no less

4. Format each entry EXACTLY as:
   **[Exact Display Name from bold text]** ([Exact page/timestamp from context]) - [2-3 sentence description]

Present the relevant resources to help the user explore these materials."""
                else:
                    # Teacher mode: Focus on explaining and teaching
                    full_prompt = f"""Based on the following context, please provide a comprehensive answer about HR and organizational development.

{context_prompt}

Question: {query}

IMPORTANT INSTRUCTIONS (TEACHER MODE):
1. Present information with the authoritative confidence of Dave Ulrich's decades of organizational research
2. Extract frameworks, dimensions, and lists exactly as they appear in the source materials
3. Use Dave Ulrich's direct, business-focused communication style - no hedging or tentative language
4. Structure responses with clear frameworks and practical applications
5. Focus on actionable insights that drive organizational effectiveness
6. Avoid phrases like "However, this may not be complete" or "additional factors may exist"

Provide a comprehensive, authoritative response in Dave Ulrich's voice based on the context above."""

            # Import the configurable system prompt
            from ..config.system_prompt import get_system_prompt

            # Choose system prompt based on context
            if context and context.get('type') == 'lesson':
                # For lessons, use a tutor-focused system prompt
                system_prompt = """You are an expert AI tutor helping students learn. Your role is to:

1. Explain concepts clearly and patiently
2. Use relatable examples and analogies
3. Break down complex topics into digestible parts
4. Encourage learning and understanding
5. Answer questions directly while relating to the lesson material
6. Provide practice problems when appropriate
7. Be supportive and encouraging

You should be knowledgeable, patient, and focused on helping the student truly understand the material."""
            else:
                # For general queries, use the configurable system prompt
                system_prompt = get_system_prompt()

            # Use async streaming
            import openai as openai_module
            client = openai_module.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response_stream = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1500,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ],
                temperature=0.7,
                stream=True
            )

            # Yield chunks as they come
            async for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            # Log analytics
            await self.log_analytics(query, {"streaming": True}, session_id)

        except Exception as e:
            logger.error(f"Error in streaming query: {e}")
            yield "I apologize, but I'm having trouble generating a response. Please try again."

    async def generate_response(self, prompt: str) -> str:
        """Generate response using OpenAI"""

        try:
            # Import the configurable system prompt
            from ..config.system_prompt import get_system_prompt

            response = openai.chat.completions.create(
                model="gpt-4o-mini",  # Use GPT-4o-mini for faster responses
                max_tokens=1500,
                messages=[
                    {
                        "role": "system",
                        "content": get_system_prompt()
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return "I apologize, but I'm having trouble generating a response right now. Please try again."
    
    def format_sources_enhanced(self, context_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format source references with enhanced metadata including file URLs - LIMITED TO 4"""
        
        sources = []
        seen_combinations = set()
        
        # Process chunks first (most specific) - limit to 4
        for chunk in context_data.get("chunks", [])[:4]:
            # Extract metadata
            metadata = chunk.metadata if hasattr(chunk, 'metadata') else {}
            
            # Get filename and title
            doc_filename = metadata.get('filename', '') or metadata.get('document_name', '')
            doc_title = metadata.get('title', '') or metadata.get('display_name', '')
            
            # Get other metadata
            raw_section = metadata.get('section', '')
            section_title = self._format_document_source(raw_section)
            page_num = metadata.get('page_number')
            file_url = metadata.get('file_url', '')
            
            # Create unique identifier to avoid duplicates (use raw section for consistency)
            source_key = f"{doc_filename}_{raw_section}_{page_num}"
            if source_key in seen_combinations:
                continue
            seen_combinations.add(source_key)
            
            # Use title if available, otherwise clean filename
            display_name = doc_title if doc_title else self.name_mapper.get_display_name(doc_filename)
            
            # Generate a concise relevance summary
            content_preview = metadata.get('content', '')
            relevance_summary = self._generate_relevance_summary(content_preview, section_title)
            
            start_time = metadata.get('start_time')
            end_time = metadata.get('end_time')
            content_type = metadata.get('content_type')
            
            logger.info(f"Processing source - filename: {doc_filename}, content_type: {content_type}, start_time: {start_time}, end_time: {end_time}")
            
            sources.append({
                "title": display_name,
                "filename": doc_filename,
                "content": relevance_summary,
                "score": float(chunk.score) if hasattr(chunk, 'score') else 0.85,
                "chunk_id": chunk.id if hasattr(chunk, 'id') else None,
                "page_number": page_num,
                "section": section_title,
                "document_id": metadata.get('document_id'),
                "type": metadata.get('chunk_type', 'chunk'),
                "fileUrl": file_url,
                "start_time": start_time,
                "end_time": end_time
            })
        
        # Sort by score (highest first)
        sources.sort(key=lambda x: x['score'], reverse=True)
        
        # Strictly limit to 4 sources
        return sources[:4]
    
    def _generate_relevance_summary(self, content: str, section: str) -> str:
        """Generate a one-sentence summary of why this content is relevant"""
        
        # Clean up the content - don't truncate for relevance summary
        content_clean = content.strip()[:500]  # Allow more content for better topic extraction
        
        # If section title is informative, use it
        if section and section != "Main Content":
            key_topic = self._extract_key_topic(content_clean)
            return f"Discusses {section} with insights on {key_topic}"
        
        # Extract key concepts from the content
        key_topic = self._extract_key_topic(content_clean)
        
        # Generate a concise summary based on content patterns
        content_lower = content_clean.lower()
        
        if "definition" in content_lower or "is defined as" in content_lower:
            return f"Defines key concepts related to {key_topic}"
        elif "example" in content_lower or "case" in content_lower:
            return f"Provides examples and case studies about {key_topic}"
        elif "how to" in content_lower or "steps" in content_lower or "process" in content_lower:
            return f"Explains practical approaches for {key_topic}"
        elif "importance" in content_lower or "critical" in content_lower or "essential" in content_lower:
            return f"Highlights the importance of {key_topic}"
        elif "challenge" in content_lower or "problem" in content_lower or "issue" in content_lower:
            return f"Addresses challenges related to {key_topic}"
        elif "benefit" in content_lower or "advantage" in content_lower or "value" in content_lower:
            return f"Outlines benefits and value of {key_topic}"
        elif "strategy" in content_lower or "strategic" in content_lower:
            return f"Presents strategic considerations for {key_topic}"
        elif "best practice" in content_lower or "recommendation" in content_lower:
            return f"Recommends best practices for {key_topic}"
        else:
            return f"Provides insights on {key_topic}"
    
    def _extract_key_topic(self, text: str) -> str:
        """Extract the main topic from a text snippet"""
        
        # Common HR/organizational keywords to look for
        keywords = [
            'leadership', 'culture', 'organization', 'talent', 'performance',
            'strategy', 'capability', 'transformation', 'development', 'engagement',
            'customer', 'innovation', 'change', 'effectiveness', 'management',
            'team', 'collaboration', 'communication', 'skills', 'competency',
            'assessment', 'metrics', 'accountability', 'alignment', 'execution'
        ]
        
        text_lower = text.lower()
        found_keywords = [kw for kw in keywords if kw in text_lower]
        
        if found_keywords:
            # Return the most relevant keyword (first found)
            return found_keywords[0]
        
        # Extract first meaningful noun phrase
        words = text.split()[:10]
        meaningful_words = [w for w in words if len(w) > 4 and w.isalpha()]
        
        if meaningful_words:
            return meaningful_words[0].lower()
        
        return "organizational practices"
    
    def _is_structured_query(self, query: str) -> bool:
        """Detect if query is asking for structured content like lists or steps"""
        structured_keywords = [
            'dimensions', 'steps', 'list', 'factors', 'elements', 'components',
            'aspects', 'ways', 'methods', 'stages', 'phases', 'points',
            'how to build', 'how to create', 'how to develop', 'process',
            'framework', 'model', 'approach', 'strategy', 'plan', 'improve',
            'six steps', 'six-step', 'logic'
        ]
        
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in structured_keywords)
    
    async def _get_sequential_chunks(self, documents: List[Dict], index) -> List[Dict]:
        """Get sequential chunks from the same document to capture complete lists"""
        
        try:
            # Group documents by filename and page
            doc_groups = {}
            for doc in documents[:3]:  # Only process top 3 for performance
                key = f"{doc['filename']}_{doc.get('page_number', 'unknown')}"
                if key not in doc_groups:
                    doc_groups[key] = []
                doc_groups[key].append(doc)
            
            enhanced_docs = list(documents)  # Start with original documents
            
            # For each group, try to get sequential chunks
            for group_key, group_docs in doc_groups.items():
                if not group_docs or not group_docs[0].get('chunk_id'):
                    continue
                    
                # Extract the numeric part of chunk_id to find sequential chunks
                base_chunk_id = group_docs[0]['chunk_id']
                logger.info(f"Looking for sequential chunks around: {base_chunk_id}")
                
                # Try to find sequential chunks by modifying the chunk ID
                sequential_ids = []
                if '_' in base_chunk_id:
                    parts = base_chunk_id.split('_')
                    if len(parts) >= 2 and parts[-1].isdigit():
                        base_num = int(parts[-1])
                        filename_part = '_'.join(parts[:-1])
                        
                        # Get a wider range for numbered sequences (like "six steps", "10 dimensions")
                        # Check if this looks like it might be part of a numbered sequence
                        content_lower = str(doc.get('content', '')).lower()
                        is_numbered_sequence = any(num in content_lower
                                                 for num in ['4.1', '4.2', '4.3', '4.4', '4.5', '4.6',
                                                           'step 1', 'step 2', 'step 3', 'step 4', 'step 5', 'step 6',
                                                           'dimension', 'dimensions'])

                        if is_numbered_sequence:
                            # More aggressive search for numbered sequences
                            # For "10 dimensions" type queries, fetch up to 15 chunks before and after
                            for offset in range(-15, 16):  # Much wider range for complete lists
                                if offset != 0:
                                    seq_id = f"{filename_part}_{base_num + offset}"
                                    sequential_ids.append(seq_id)
                        else:
                            # Normal range for other structured content
                            for offset in [-2, -1, 1, 2, 3]:
                                seq_id = f"{filename_part}_{base_num + offset}"
                                sequential_ids.append(seq_id)
                
                # Fetch sequential chunks
                if sequential_ids:
                    try:
                        fetch_results = index.fetch(sequential_ids)
                        for seq_id, vector_data in fetch_results.vectors.items():
                            if vector_data and hasattr(vector_data, 'metadata'):
                                # Add sequential chunk if it doesn't already exist
                                existing_ids = {doc.get('chunk_id') for doc in enhanced_docs}
                                if seq_id not in existing_ids:
                                    enhanced_docs.append({
                                        'content': vector_data.metadata.get('content', ''),
                                        'title': vector_data.metadata.get('title', ''),
                                        'filename': vector_data.metadata.get('filename', ''),
                                        'page_number': vector_data.metadata.get('page_number', ''),
                                        'score': 0.5,  # Lower score for sequential chunks
                                        'chunk_id': seq_id
                                    })
                                    
                        logger.info(f"Added {len(fetch_results.vectors)} sequential chunks for {group_key}")
                        
                        # Log some content to verify we're getting the right chunks
                        for seq_id, vector_data in list(fetch_results.vectors.items())[:2]:
                            content_preview = vector_data.metadata.get('content', '')[:100] if vector_data else ''
                            logger.info(f"Sequential chunk {seq_id}: {content_preview}...")
                        
                    except Exception as fetch_error:
                        logger.warning(f"Could not fetch sequential chunks: {fetch_error}")
            
            # Sort by score (original matches first, then sequential)
            enhanced_docs.sort(key=lambda x: x['score'], reverse=True)
            
            # Increased limit for numbered sequences and dimension queries
            max_docs = 30 if any('4.1' in str(doc.get('content', '')) or
                                'step' in str(doc.get('content', '')).lower() or
                                'dimension' in str(doc.get('content', '')).lower()
                               for doc in enhanced_docs) else 15
            
            logger.info(f"Returning {min(len(enhanced_docs), max_docs)} documents (max: {max_docs})")
            return enhanced_docs[:max_docs]
            
        except Exception as e:
            logger.error(f"Error getting sequential chunks: {e}")
            return documents  # Return original if error

    async def _filter_allowed_documents(self, documents: List[Dict]) -> List[Dict]:
        """Filter out documents that shouldn't be shown in RAG results (e.g., AI training only documents)"""
        try:
            if not db.engine:
                logger.warning("No database connection - skipping document filtering")
                return documents

            from sqlalchemy import text

            # Get list of filenames that should NOT be shown (show_in_viewer = FALSE)
            with db.engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT filename
                        FROM document_metadata
                        WHERE show_in_viewer = FALSE
                    """)
                )

                blocked_filenames = {row[0] for row in result}

            # Filter OUT documents that are explicitly blocked
            # Allow all documents that are either:
            # 1. Not in the database (new documents)
            # 2. In the database with show_in_viewer = TRUE
            filtered_docs = [
                doc for doc in documents
                if doc.get('filename') not in blocked_filenames and doc.get('title') not in blocked_filenames
            ]

            if len(filtered_docs) < len(documents):
                logger.info(f"Filtered out {len(documents) - len(filtered_docs)} AI-training-only documents")

            return filtered_docs

        except Exception as e:
            logger.error(f"Error filtering documents: {e}")
            # Return original documents if filtering fails
            return documents

    def format_sources(self, context_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Legacy format_sources method for backward compatibility"""
        return self.format_sources_enhanced(context_data)
    
    async def log_analytics(self, query: str, response: Dict[str, Any], session_id: Optional[str]):
        """Log analytics for the query"""
        
        try:
            if db.engine:
                from sqlalchemy import text
                
                with db.engine.connect() as conn:
                    conn.execute(
                        text("""
                            INSERT INTO analytics_events (event_type, event_data, session_id, created_at)
                            VALUES (:event_type, :event_data, :session_id, :created_at)
                        """),
                        {
                            'event_type': 'chat_query',
                            'event_data': json.dumps({
                                'query': query,
                                'response_length': len(response.get('answer', '')),
                                'num_sources': len(response.get('sources', [])),
                                'has_error': 'error' in response
                            }),
                            'session_id': session_id,
                            'created_at': datetime.now()
                        }
                    )
                    conn.commit()
                    
        except Exception as e:
            logger.error(f"Error logging analytics: {e}")

# Create global chat service instance
chat_service = ChatService()