from pinecone import Pinecone
from openai import OpenAI
from dotenv import load_dotenv
import os
import logging
from typing import List, Dict, Any

load_dotenv()

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self):
        try:
            # Initialize Pinecone
            self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
            
            # Initialize OpenAI for embeddings
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
            # Use your existing index - get name from env or default
            self.index_name = os.getenv("PINECONE_INDEX_NAME", "ulrich-ai")
            self.index = self.pc.Index(
                name=self.index_name,
                host=os.getenv("PINECONE_HOST")
            )
            
            logger.info("Vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise
    
    def create_indexes(self):
        """Check if index exists and is ready"""
        try:
            stats = self.index.describe_index_stats()
            logger.info(f"Index {self.index_name} ready with {stats['total_vector_count']} vectors")
        except Exception as e:
            logger.error(f"Error checking index: {e}")
    
    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI"""
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=text,
                dimensions=1024  # Specify 1024 dimensions
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        try:
            # OpenAI can handle batch requests
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-large",
                input=texts,
                dimensions=1024
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            raise

    def delete_by_filename(self, filename: str) -> Dict[str, Any]:
        """Delete all vectors associated with a filename from all Pinecone namespaces"""
        try:
            logger.info(f"Deleting vectors for filename: {filename}")

            # Delete from all namespaces where document data is stored
            namespaces = ['chunks', 'sections', 'documents']
            deleted_namespaces = []
            errors = []

            for namespace in namespaces:
                try:
                    # Delete by metadata filter in each namespace
                    self.index.delete(
                        filter={
                            "filename": {"$eq": filename}
                        },
                        namespace=namespace
                    )
                    deleted_namespaces.append(namespace)
                    logger.info(f"Deleted vectors for {filename} from namespace '{namespace}'")
                except Exception as ns_error:
                    # Log but continue with other namespaces
                    logger.warning(f"Could not delete from namespace '{namespace}': {ns_error}")
                    errors.append(f"{namespace}: {str(ns_error)}")

            # Also try the default namespace (no namespace specified) for backwards compatibility
            try:
                self.index.delete(
                    filter={
                        "filename": {"$eq": filename}
                    }
                )
                deleted_namespaces.append("default")
                logger.info(f"Deleted vectors for {filename} from default namespace")
            except Exception as default_error:
                logger.warning(f"Could not delete from default namespace: {default_error}")

            logger.info(f"Successfully deleted vectors for {filename} from namespaces: {deleted_namespaces}")
            return {
                "status": "success",
                "filename": filename,
                "namespaces_deleted": deleted_namespaces,
                "errors": errors if errors else None,
                "message": f"Deleted all vectors for {filename}"
            }

        except Exception as e:
            logger.error(f"Error deleting vectors for {filename}: {e}")
            raise

# Create global vector store instance
vector_store = VectorStore()