import base64
import io
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

# Requests is used for HTTP requests to the Confluence REST API
import requests
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# === CONFIGURATION ===
# All configuration is now pulled from environment variables for portability
CONFLUENCE_BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "").rstrip('/') # Ensure no trailing slash
API_USER_EMAIL = os.environ.get("CONFLUENCE_USER_EMAIL")
USERNAME = os.environ.get("CONFLUENCE_USERNAME", "")  # optional, not used in Bearer auth
API_TOKEN = os.environ.get("CONFLUENCE_PAT", "").strip()  # API token, strip whitespace
SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY")
PARENT_PAGE_TITLE = os.environ.get("CONFLUENCE_PARENT_TITLE")

# Common headers for all API requests (Bearer token auth)
COMMON_HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# Debug configuration
print(f"DEBUG: Using Base URL: {CONFLUENCE_BASE_URL}")
print(f"DEBUG: Space Key: {SPACE_KEY}")
if API_TOKEN:
    print(f"DEBUG: Token loaded: Yes (Starts with: {API_TOKEN[:5]}...)")
else:
    print("DEBUG: Token loaded: No")

# Path to CA certificates for SSL verification (can override with env if needed)
# Defaulting to False (insecure) because internal CA certs are often not in Python's bundle.
# Set CONFLUENCE_CERT_PATH to the path of your corporate CA bundle to enable verification.
CERT_PATH = os.environ.get("CONFLUENCE_CERT_PATH") 

# Disable warnings for insecure requests if verification is disabled
if not CERT_PATH:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_page_id_by_title(title: str) -> str:
    """
    Returns the page ID for a given title in a Confluence space using hardcoded config.
    Raises an exception if the page is not found or the request fails.
    """
    if not CONFLUENCE_BASE_URL or not SPACE_KEY:
         raise ValueError("Missing configuration: CONFLUENCE_BASE_URL or SPACE_KEY not set.")

    url = f"{CONFLUENCE_BASE_URL}/rest/api/content"
    params = {"title": title, "spaceKey": SPACE_KEY, "expand": "ancestors"}
    
    # Use verify=CERT_PATH only if it's set, otherwise False (insecure but working)
    verify_ssl = CERT_PATH if CERT_PATH else False

    response = requests.get(
        url,
        params=params,
        verify=verify_ssl,
        headers=COMMON_HEADERS,
    )
    # Check for HTTP errors
    if response.status_code != 200:
        raise Exception(
            f"Failed to fetch page ID: {response.status_code} {response.text}"
        )
    
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        # If headers are wrong, we might get an HTML login page.
        print(f"DEBUG: Failed to decode JSON. Response text preview:\n{response.text[:500]}...")
        raise
        
    # Check if the page exists
    if data["size"] == 0:
        raise Exception(f"No page found with title '{title}' in space '{SPACE_KEY}'")
    # Return the first matching page's ID
    return data["results"][0]["id"]


def new_page(title: str, content: str, parent: str = PARENT_PAGE_TITLE):
    """
    Creates a Confluence page under the parent page with the given title.
    If the page already exists under the parent, replaces its content.
    Args:
        parent: The title of the parent (ancestor) page.
        title: The title of the new page to create or update.
        content: The HTML content for the new page.
    """
    verify_ssl = CERT_PATH if CERT_PATH else False

    # Get the parent page's ID by title
    try:
        parent_id = get_page_id_by_title(parent)
    except Exception as e:
        print(f"Error finding parent page '{parent}': {e}")
        return

    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/"
    headers = {"Content-Type": "application/json", **COMMON_HEADERS}

    # Check if the page already exists under the parent
    params = {"title": title, "spaceKey": SPACE_KEY, "expand": "ancestors,version"}
    resp = requests.get(
        url[:-1], params=params, verify=verify_ssl, headers=COMMON_HEADERS
    )
    page_exists = False
    page_id = None
    version = 1
    if resp.status_code == 200:
        data = resp.json()
        for result in data.get("results", []):
            ancestors = result.get("ancestors", [])
            # Only update if the ancestor matches the parent
            if ancestors and ancestors[-1]["id"] == parent_id:
                page_exists = True
                page_id = result["id"]
                version = result["version"]["number"] + 1
                break

    if page_exists:
        # Update existing page (PUT request)
        update_url = f"{url}{page_id}"
        payload = {
            "id": page_id,
            "type": "page",
            "title": title,
            "ancestors": [{"id": parent_id}],
            "space": {"key": SPACE_KEY},
            "body": {"storage": {"value": content, "representation": "storage"}},
            "version": {"number": version},
        }
        response = requests.put(
            update_url,
            json=payload,
            headers=headers,
            verify=verify_ssl,
        )
        if response.status_code == 200:
            print("Page updated successfully!")
            print("URL:", CONFLUENCE_BASE_URL + response.json()["_links"]["webui"])
        else:
            print("Failed to update page")
            print("Status Code:", response.status_code)
            print("Response:", response.text)
    else:
        # Create new page (POST request)
        payload = {
            "type": "page",
            "title": title,
            "ancestors": [{"id": parent_id}],
            "space": {"key": SPACE_KEY},
            "body": {"storage": {"value": content, "representation": "storage"}},
        }
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            verify=verify_ssl,
        )
        if response.status_code == 200 or response.status_code == 201:
            print("Page created successfully!")
            print("URL:", CONFLUENCE_BASE_URL + response.json()["_links"]["webui"])
        else:
            print("Failed to create page")
            print("Status Code:", response.status_code)
            print("Response:", response.text)


def encode_matplotlib_fig(fig) -> bytes:
    """Turns a matplotlib figure into png bytes"""
    image = io.BytesIO()  # acts like a file
    fig.savefig(image, format="png", pad_inches=0, bbox_inches="tight")
    image.seek(0)  # at this point, `image` is a bunch of bytes that is a png
    return image.read()


def upload_attachment_to_page(
    page_id: str, filename: str, file_bytes: bytes, mime_type: str = "image/png"
):
    """
    Uploads a file as an attachment to the specified Confluence page.
    If an attachment with the same filename exists, it will be replaced (updated).
    Returns the attachment info (JSON) or raises an exception on failure.
    """
    verify_ssl = CERT_PATH if CERT_PATH else False
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/child/attachment"
    headers = {"X-Atlassian-Token": "no-check", **COMMON_HEADERS}
    files = {"file": (filename, file_bytes, mime_type)}
    # Try to upload as new attachment
    response = requests.post(url, headers=headers, files=files, verify=verify_ssl)
    if response.status_code == 400 and "same file name" in response.text:
        # Attachment exists, update it
        # Get the attachment ID
        att_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/child/attachment?filename={filename}&expand=results"
        att_resp = requests.get(att_url, headers=COMMON_HEADERS, verify=verify_ssl)
        if att_resp.status_code == 200:
            results = att_resp.json().get("results", [])
            if results:
                att_id = results[0]["id"]
                update_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/child/attachment/{att_id}/data"
                update_resp = requests.post(
                    update_url, headers=headers, files=files, verify=verify_ssl
                )
                if update_resp.status_code in (200, 201):
                    return update_resp.json()
                else:
                    raise Exception(
                        f"Failed to update attachment: {update_resp.status_code} {update_resp.text}"
                    )
        raise Exception(
            f"Failed to find existing attachment to update: {att_resp.status_code} {att_resp.text}"
        )
    elif response.status_code not in (200, 201):
        raise Exception(
            f"Failed to upload attachment: {response.status_code} {response.text}"
        )
    return response.json()


def generate_sample_data_and_plot():
    """
    Generates a sample pandas DataFrame and a matplotlib plot, returns both as HTML strings.
    The plot is uploaded as an attachment and referenced in the page content.
    """
    # Create sample data
    df = pd.DataFrame({"Category": ["A", "B", "C", "D"], "Value": [23, 45, 12, 36]})
    # Create a bar plot
    fig, ax = plt.subplots(figsize=(4, 3), dpi=150)
    df.plot(
        kind="bar",
        x="Category",
        y="Value",
        ax=ax,
        legend=False,
        color="skyblue",
    )
    ax.set_title("Sample Bar Plot")
    ax.set_ylabel("Value")
    plt.tight_layout()
    img_bytes = encode_matplotlib_fig(fig)
    plt.close(fig)
    # DataFrame as HTML table
    table_html = df.to_html(
        index=False, border=0, classes="confluenceTable", justify="center"
    )
    return table_html, img_bytes


def create_confluence_automation_page():
    """
    Creates or updates a Confluence page titled 'Confluence Automation' under the default parent.
    The page will contain:
      1. A notice that the page was created from Python using this script.
      2. A disclaimer that the script was largely written by GitHub Copilot and is not optimized.
      3. Instructions for generating a Confluence API token.
      4. A sample pandas DataFrame and matplotlib plot, both embedded in the page.
      5. The full code of this module as a code block.
      6. Example usage instructions for copying and running the script.
    """
    # Validate env vars
    if not all([CONFLUENCE_BASE_URL, API_TOKEN, SPACE_KEY, PARENT_PAGE_TITLE]):
        print("Missing required environment variables. Please check configuration.")
        return

    # Disclaimer and notice at the top of the page
    disclaimer = (
        '<div style="border:2px solid #c33; padding:10px; background:#fee; margin-bottom:10px;">'
        "<b>DISCLAIMER:</b> This script was largely written by GitHub Copilot and is not optimized for production use. Review and adapt as needed."
        "</div>"
    )
    notice = (
        '<div style="border:2px solid #36c; padding:10px; background:#eef; margin-bottom:20px;">'
        "<b>NOTE:</b> This entire Confluence page was created and updated from Python using the script below. Do not modify manually in Confluence!"
        "</div>"
    )
    # Updated instructions for generating a Confluence API token with enterprise link
    instructions = """
<h2>How to Generate a Confluence API Token</h2>
<p>To use this script, you need a Confluence API token. For enterprise Confluence, follow your organization's process or see the official documentation:<br/>
<a href='https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html#UsingPersonalAccessTokens-CreatingPATsintheapplication' target='_blank'>How to create a Personal Access Token in Confluence</a></p>
<ol>
  <li>Generate or obtain your Confluence API token using your enterprise Confluence UI or the link above.</li>
  <li>Set the following environment variables in your shell:<br/>
    <code>export CONFLUENCE_BASE_URL=your_confluence_url</code><br/>
    <code>export CONFLUENCE_USER_EMAIL=your_email</code><br/>
    <code>export CONFLUENCE_PAT=your_api_token</code><br/>
    <code>export CONFLUENCE_SPACE_KEY=your_space_key</code> <span style='color:#888'>(see below)</span><br/>
    <code>export CONFLUENCE_PARENT_TITLE=your_parent_page_title</code><br/>
    <span style='color:#888'>(Optional) <code>export CONFLUENCE_CERT_PATH=/path/to/certs</code></span>
  </li>
</ol>
<p>These variables are required for authenticating and configuring API requests from this script.</p>
<h3>How to find your <code>space_key</code></h3>
<p>The <b>space_key</b> is usually visible in the URL when viewing a Confluence page. For example, in a URL like:<br/>
<code>https://wiki.ith.intel.com/display/<b>DefmetYieldResources</b>/Confluence+Automation</code><br/>
The value after <code>/display/</code> and before the next <code>/</code> is your <b>space_key</b> (here: <code>DefmetYieldResources</code>).</p>
"""
    # Read this file's code and escape CDATA end markers
    with open(__file__, "r", encoding="utf-8") as f:
        code = f.read()
    
    # Simple escaping for XML/HTML in the code block
    code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    code_block = f'<ac:structured-macro ac:name="code"><ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>'
    example_usage = """
<h2>How to Use This Script</h2>
<ol>
  <li>Copy the code above into a file named <code>confluence.py</code> on your machine.</li>
  <li>Make sure you have <b>Python 3</b> and the <b>requests</b> library installed.</li>
  <li>Set the required environment variables as shown above.</li>
  <li>Run the script:<br/>
      <code>python confluence.py</code></li>
</ol>
"""
    table_html, img_bytes = generate_sample_data_and_plot()
    # Get the page ID (will create/update page after this)
    # parent_id = get_page_id_by_title(PARENT_PAGE_TITLE) 
    # ^ Not needed to call explicitly here, new_page calls it.
    
    # Create or update the page first to get its ID
    # (We need the page to exist before uploading the attachment)
    # Temporarily use a placeholder for the image macro
    img_html = "<p><i>Uploading plot...</i></p>"
    sample_section = f"""
<h2>Sample Data and Plot</h2>
<p>This section demonstrates embedding a pandas DataFrame as an HTML table and a matplotlib plot as an attachment image:</p>
<h3>Sample Data Table</h3>
{table_html}
<h3>Sample Plot</h3>
{img_html}
"""
    content = (
        disclaimer
        + notice
        + instructions
        + sample_section
        + "<h2>Script Source Code</h2>"
        + code_block
        + example_usage
    )
    # Create or update the page (get its ID)
    new_page("Confluence Automation", content)
    
    # Get the page ID for the new/updated page
    page_id = get_page_id_by_title("Confluence Automation")
    
    # Upload the plot as an attachment
    upload_attachment_to_page(page_id, "plot.png", img_bytes)
    
    # Now update the page again, referencing the attachment
    img_html = '<ac:image><ri:attachment ri:filename="plot.png"/></ac:image>'
    sample_section = f"""
<h2>Sample Data and Plot</h2>
<p>This section demonstrates embedding a pandas DataFrame as an HTML table and a matplotlib plot as an attachment image:</p>
<h3>Sample Data Table</h3>
{table_html}
<h3>Sample Plot</h3>
{img_html}
"""
    # Add a section explaining how image uploading works
    image_upload_explanation = """
<h2>How Image Uploading Works</h2>
<p>This script demonstrates how to programmatically upload images to Confluence pages using the REST API. The process is as follows:</p>
<ol>
  <li><b>Generate the image</b> (e.g., a matplotlib plot) in Python and keep it in memory as PNG bytes.</li>
  <li><b>Create or update the Confluence page</b> to ensure it exists and obtain its page ID.</li>
  <li><b>Upload the image as an attachment</b> to the page using the <code>/rest/api/content/&lt;page_id&gt;/child/attachment</code> endpoint. This is done with a POST request containing the image file bytes and the <code>X-Atlassian-Token: no-check</code> header.</li>
  <li><b>Reference the uploaded image</b> in the page content using the <code>&lt;ac:image&gt;&lt;ri:attachment ri:filename="plot.png"/&gt;&lt;/ac:image&gt;</code> macro, which tells Confluence to display the attached image inline.</li>
</ol>
<p>This approach is required because Confluence does not support inline base64-encoded images for security reasons. Images must be attached to the page and referenced by filename.</p>
"""
    # Add an intro explaining what this document is about
    intro = """
<h1>Confluence Automation Example</h1>
<p>This page demonstrates how to automate the creation and updating of Confluence pages using Python. It shows how to:
<ul>
  <li>Configure all settings via environment variables for portability</li>
  <li>Embed a pandas DataFrame as an HTML table</li>
  <li>Generate and upload a matplotlib plot as an image attachment</li>
  <li>Reference the uploaded image inline in the page</li>
  <li>Provide full usage instructions and code for reproducibility</li>
</ul>
This document and the code below are intended as a portable, self-contained example for automating Confluence content generation and image embedding.</p>
"""
    content = (
        intro
        + disclaimer
        + notice
        + instructions
        + image_upload_explanation
        + sample_section
        + "<h2>Script Source Code</h2>"
        + code_block
        + example_usage
    )
    new_page("Confluence Automation", content)


if __name__ == "__main__":
    # Ultra simple: just create/update the Confluence Automation page when run
    create_confluence_automation_page()
