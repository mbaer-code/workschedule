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

    import sys
    print("[DEBUG] Entered process_pdf_documentai_from_bytes")
    PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT_ID", "work-schedule-cloud")
    LOCATION = os.environ.get("DOCUMENT_AI_LOCATION", "us")
    PROCESSOR_ID = os.environ.get("DOCUMENT_AI_PROCESSOR_ID", "fe0baaa28beedbe9")
    print(f"[DEBUG] ENV VARS: GOOGLE_CLOUD_PROJECT_ID={PROJECT_ID}, DOCUMENT_AI_LOCATION={LOCATION}, DOCUMENT_AI_PROCESSOR_ID={PROCESSOR_ID}")

    if not PROJECT_ID or not PROCESSOR_ID:
        sys.stderr.write(f"[ERROR] PROJECT_ID or PROCESSOR_ID not configured. PROJECT_ID={PROJECT_ID}, PROCESSOR_ID={PROCESSOR_ID}\n")
        return None, None

    try:
        print("[DEBUG] Creating DocumentAI client options...")
        client_options = ClientOptions(api_endpoint=f"{LOCATION}-documentai.googleapis.com")
        print("[DEBUG] Initializing DocumentProcessorServiceClient...")
        documentai_client = documentai.DocumentProcessorServiceClient(client_options=client_options)
        print("[DEBUG] Building processor path...")
        name = documentai_client.processor_path(PROJECT_ID, LOCATION, PROCESSOR_ID)

        print("[DEBUG] Creating RawDocument...")
        raw_document = documentai.RawDocument(
            content=file_contents,
            mime_type="application/pdf"
        )

        print("[DEBUG] Building ProcessRequest...")
        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_document
        )

        print(f"[DEBUG] DocumentAI request: name={name}, raw_document.mime_type={raw_document.mime_type}, raw_document.content_length={len(file_contents)}")
        print("[DEBUG] Processing document from memory...")
        response = documentai_client.process_document(request=request)
        print(f"[DEBUG] DocumentAI response received. Response type: {type(response)}")
        document = response.document
        print(f"[DEBUG] DocumentAI document: text_length={len(document.text) if document.text else 0}, entity_count={len(document.entities) if document.entities else 0}")
        extracted_text = document.text
        entities = document.entities
        print("[DEBUG] Document AI processing complete.")
        return extracted_text, entities
    except Exception as e:
        import traceback
        sys.stderr.write(f"[ERROR] Exception during DocumentAI processing: {e}\n")
        sys.stderr.write(traceback.format_exc())
        return None, None
