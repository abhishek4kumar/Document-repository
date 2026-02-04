import os
import sys

# Import functions from your existing automation script
try:
    from confluence_automation import new_page, upload_attachment_to_page, get_page_id_by_title, PARENT_PAGE_TITLE
except ImportError:
    print("Error: Could not import 'confluence_automation.py'. Make sure it is in the same folder.")
    sys.exit(1)

def upload_skill_file(file_path: str, page_title: str = None):
    """
    Reads a SKILL file (.il or .ils), creates a Confluence page with the code embedded, 
    and uploads the file as an attachment.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at '{file_path}'")
        return

    filename = os.path.basename(file_path)
    
    # If no title provided, use the filename (without extension if preferred, or full name)
    if not page_title:
        page_title = filename

    print(f"\nProcessing: {filename}")
    print(f"Target Page: '{page_title}'")
    print(f"Parent Page: '{PARENT_PAGE_TITLE}'")

    # 1. Read file content
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            file_content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 2. Prepare Page Content
    # We use pure CDATA and only escape the CDATA closing tag if it appears in the code.
    safe_content = file_content.replace('\r\n', '\n')
    safe_content = safe_content.replace(']]>', ']]]]><![CDATA[>')
    
    # Confluence XML Storage Format
    # We use the 'code' macro to display the script nicely
    html_content = f"""
    <p>This page documents the SKILL script <b>{filename}</b>.</p>
    
    <h3>File Attachment</h3>
    <p>
      <ac:link>
        <ri:attachment ri:filename="{filename}" />
        <ac:plain-text-link-body><![CDATA[Download {filename}]]></ac:plain-text-link-body>
      </ac:link>
    </p>

    <h3>Source Code</h3>
    <ac:structured-macro ac:name="code">
        <ac:parameter ac:name="language">lisp</ac:parameter> 
        <ac:parameter ac:name="linenumbers">true</ac:parameter>
        <ac:plain-text-body><![CDATA[{safe_content}]]></ac:plain-text-body>
    </ac:structured-macro>
    """

    # 3. Create or Update the Page
    print("Creating/Updating page wrapper...")
    # Note: This function prints status to console
    new_page(page_title, html_content)
    
    # 4. Get Page ID (needed for attachment upload)
    try:
        page_id = get_page_id_by_title(page_title)
    except Exception as e:
        print(f"Error getting page ID: {e}")
        return

    # 5. Upload the .ils file as an attachment
    print(f"Uploading '{filename}' as attachment...")
    with open(file_path, 'rb') as f:
        file_bytes = f.read()
    
    try:
        # MIME type 'text/plain' allows it to be previewed in browser often
        upload_attachment_to_page(page_id, filename, file_bytes, mime_type="text/plain")
        print("Attachment uploaded successfully.")
    except Exception as e:
        print(f"Error uploading attachment: {e}")

    print(f"\nSUCCESS! Page available at: {os.environ.get('CONFLUENCE_BASE_URL')}/display/{os.environ.get('CONFLUENCE_SPACE_KEY')}/{page_title.replace(' ', '+')}")

if __name__ == "__main__":
    # === SETTINGS ===
    # Change these variables to match your file
    
    # 1. The path to your .ils file
    MY_FILE_PATH = "C:\\Users\\a07\\OneDrive - Intel Corporation\\Desktop\\Skilltest\\x76_nyratest -txt\\QreEMLegoXY\\TccClassQreEMLegoXY.ils" 
    
    # 2. The title of the new sub-page to create
    MY_PAGE_TITLE = "My SKILL Script (Example)"

    # Create a dummy file for testing if it doesn't exist
    if not os.path.exists(MY_FILE_PATH):
        with open(MY_FILE_PATH, "w") as f:
            f.write("; This is a sample .ils file\n(procedure (helloWorld)\n  (println \"Hello from Confluence!\")\n)")
            print(f"Created dummy file '{MY_FILE_PATH}' for testing.")

    # Run the upload
    upload_skill_file(MY_FILE_PATH, MY_PAGE_TITLE)
