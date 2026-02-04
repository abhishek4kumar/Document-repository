import os
import sys
import mimetypes

# Import functions from the main library
try:
    from confluence_automation import new_page, upload_attachment_to_page, get_page_id_by_title, PARENT_PAGE_TITLE
except ImportError:
    print("Error: Could not import 'confluence_automation.py'. Make sure it is in the same folder.")
    sys.exit(1)

# Define supported extensions
CODE_EXTENSIONS = ('.ils', '.il')
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.bmp')
OFFICE_EXTENSIONS = ('.pptx', '.ppt', '.xlsx', '.xls', '.docx', '.doc')
ALL_SUPPORTED_EXTENSIONS = CODE_EXTENSIONS + IMAGE_EXTENSIONS + OFFICE_EXTENSIONS

def get_content_body_for_file(filename, file_path):
    """
    Generates the HTML storage format content based on file type.
    """
    ext = os.path.splitext(filename)[1].lower()
    
    # Common Download Link used for all types
    download_section = f"""
        <h3>Download</h3>
        <p>
          <ac:link>
            <ri:attachment ri:filename="{filename}" />
            <ac:plain-text-link-body><![CDATA[Download {filename}]]></ac:plain-text-link-body>
          </ac:link>
        </p>
    """

    if ext in CODE_EXTENSIONS:
        # Code Logic (Read file, wrap in code macro)
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                raw_content = f.read()
            # Escape for CDATA
            safe_content = raw_content.replace(']]>', ']]]]><![CDATA[>')
            
            body = f"""
            <p><b>Filename:</b> {filename}</p>
            {download_section}
            <h3>Source Code</h3>
            <ac:structured-macro ac:name="code">
                <ac:parameter ac:name="language">lisp</ac:parameter> 
                <ac:parameter ac:name="linenumbers">true</ac:parameter>
                <ac:parameter ac:name="theme">Midnight</ac:parameter>
                <ac:plain-text-body><![CDATA[{safe_content}]]></ac:plain-text-body>
            </ac:structured-macro>
            """
            return body
            
        except Exception as e:
            print(f"  Error reading text file content: {e}")
            return f"<p>Error reading file content.</p>{download_section}"

    elif ext in IMAGE_EXTENSIONS:
        # Image Logic (Display image)
        body = f"""
        <p><b>Filename:</b> {filename}</p>
        <p>
            <ac:image>
                <ri:attachment ri:filename="{filename}" />
            </ac:image>
        </p>
        {download_section}
        """
        return body

    elif ext in OFFICE_EXTENSIONS:
        # Office Logic (View File macro)
        # Note: 'view-file' macro is common, but sometimes 'viewdoc', 'viewxls', 'viewppt' are preferred.
        # We'll try the generic 'view-file' which often auto-detects.
        body = f"""
        <p><b>Filename:</b> {filename}</p>
        {download_section}
        <h3>Preview</h3>
        <p>
            <ac:structured-macro ac:name="view-file">
                <ac:parameter ac:name="name"><ri:attachment ri:filename="{filename}" /></ac:parameter>
            </ac:structured-macro>
        </p>
        """
        return body

    else:
        # Fallback
        return f"<p><b>Filename:</b> {filename}</p>{download_section}"

def upload_ils_directory(directory_path: str, directory_page_title: str, section_parent_title: str = "Skill Resource"):
    """
    Creates a 3-level hierarchy:
    1. section_parent_title (e.g., 'Skill Resource') - Created under the global Parent
    2. directory_page_title (e.g., 'My Folder') - Created under Skill Resource
    3. File pages - Created under My Folder
    """
    
    if not os.path.exists(directory_path):
        print(f"Error: Directory not found at '{directory_path}'")
        return

    print(f"=== Starting Directory Upload ===")
    print(f"Source Dir:      {directory_path}")
    print(f"Section Parent:  {section_parent_title}")
    print(f"Directory Page:  {directory_page_title}")
    print(f"Global Parent:   {PARENT_PAGE_TITLE}")
    print("=================================\n")

    # --- Step 1: Ensure the Section Parent Exists (e.g., 'Skill Resource') ---
    # We create this under the PARENT_PAGE_TITLE defined in .env
    print(f"Ensuring section parent '{section_parent_title}' exists...")
    section_content = f"""
    <p>This section contains resources and libraries.</p>
    <ac:structured-macro ac:name="children" />
    """
    try:
        new_page(section_parent_title, section_content, parent=PARENT_PAGE_TITLE)
    except Exception as e:
        print(f"CRITICAL ERROR creating section parent: {e}")
        return

    # --- Step 2: Create the Directory container Page ---
    # This page will act as the folder. Created under 'section_parent_title'
    container_content = f"""
    <p>This page contains resources imported from directory: <b>{os.path.basename(directory_path)}</b></p>
    <p><i>Structure created by automation script.</i></p>
    
    <h3>Contents</h3>
    <ac:structured-macro ac:name="children" />
    """
    
    print(f"Creating directory page '{directory_page_title}' under '{section_parent_title}'...")
    try:
        new_page(directory_page_title, container_content, parent=section_parent_title)
    except Exception as e:
        print(f"CRITICAL ERROR creating directory page: {e}")
        return

    # --- Step 3: Process Files ---
    # Find all supported files
    files = [f for f in os.listdir(directory_path) if f.lower().endswith(ALL_SUPPORTED_EXTENSIONS)]
    
    if not files:
        print("No supported files found in this directory.")
        return

    print(f"Found {len(files)} supported files. Processing...")

    for filename in files:
        file_path = os.path.join(directory_path, filename)
        
        # The sub-page title will be the filename
        page_title = filename 
        
        print(f"\nProcessing file: {filename}")
        
        # Determine content body based on file type
        child_html = get_content_body_for_file(filename, file_path)

        # Create the sub-page
        # IMPORTANT: parent is now 'directory_page_title' (the page we created in Step 2)
        print(f"  Creating sub-page '{page_title}' under '{directory_page_title}'...")
        try:
            new_page(page_title, child_html, parent=directory_page_title)
        except Exception as e:
            print(f"  Error creating page: {e}")
            # If the page already exists, we might want to attach anyway?
            # For now, we continue, but we need the page ID to attach the file.
            pass

        # Upload Attachment
        try:
            # We need the ID of the specific sub-page we just created (or existing one)
            sub_page_id = get_page_id_by_title(page_title)
            
            if not sub_page_id:
                print(f"  Skipping attachment upload: Could not find page ID for '{page_title}'")
                continue

            # Guess Mime Type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"

            with open(file_path, 'rb') as f:
                file_bytes = f.read()
                
            upload_attachment_to_page(sub_page_id, filename, file_bytes, mime_type=mime_type)
            print(f"  Attachment uploaded successfully ({mime_type}).")
            
        except Exception as e:
            print(f"  Error uploading attachment: {e}")

    print("\nBatch upload complete.")

if __name__ == "__main__":
    # === INSTRUCTIONS ===
    # 1. Update TARGET_DIRECTORY to point to the folder on your computer containing .ils files
    # 2. Update DIRECTORY_PAGE_NAME to the title you want for the "Folder" page in Confluence
    # 3. Update SECTION_PAGE_NAME to the intermediate parent (e.g. 'Skill Resource')
    
    TARGET_DIRECTORY = r"C:\Users\a07\OneDrive - Intel Corporation\Desktop\Nyra BKM QRTC DOC\2025"  # Example local folder
    DIRECTORY_PAGE_NAME = "2025" # The Folder Page
    SECTION_PAGE_NAME = "TDFX" # The Intermediate Page

    # Create dummy testing data if it doesn't exist
    if not os.path.exists(TARGET_DIRECTORY):
        os.makedirs(TARGET_DIRECTORY, exist_ok=True)
        with open(os.path.join(TARGET_DIRECTORY, "example_script.ils"), "w") as f:
             f.write(";; This is a test script\n(println 'Hello-World)")
        print(f"Created a sample folder at {TARGET_DIRECTORY} for testing.")

    upload_ils_directory(TARGET_DIRECTORY, DIRECTORY_PAGE_NAME, SECTION_PAGE_NAME)
