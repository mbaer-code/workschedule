import os
from google.api_core.client_options import ClientOptions
from google.cloud import documentai_v1 as documentai

def process_pdf_documentai_from_bytes(file_contents: bytes):
    """
    Processes a PDF file from a byte stream using Document AI.
    
    Args:
        file_contents: The bytes of the PDF file.
        
    Returns:
        A tuple containing the extracted text and a list of entities, or (None, None) if an error occurs.
    """
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT_ID")
    LOCATION = os.environ.get("DOCUMENT_AI_LOCATION", "us")
    PROCESSOR_ID = os.environ.get("DOCUMENT_AI_PROCESSOR_ID")

    if not PROJECT_ID or not PROCESSOR_ID:
        print("Error: PROJECT_ID or PROCESSOR_ID not configured.")
        return None, None

    try:
        client_options = ClientOptions(api_endpoint=f"{LOCATION}-documentai.googleapis.com")
        documentai_client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        name = documentai_client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)
        
        # Use RawDocument for in-memory processing
        raw_document = documentai.RawDocument(
            content=file_contents,
            mime_type="application/pdf"
        )
        
        # Configure the process request to use raw_document
        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_document
        )

        print("Processing document from memory.")
        response = documentai_client.process_document(request=request)
        document = response.document
        extracted_text = document.text
        entities = document.entities
        print("Document AI processing complete.")
        return extracted_text, entities
    except Exception as e:
        print(f"Error processing document with Document AI: {e}")
        return None, None
