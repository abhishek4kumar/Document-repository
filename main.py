CONFLUENCE_BASE_URL=https://your-domain.atlassian.net/wiki
CONFLUENCE_USER_EMAIL=your-email@example.com
CONFLUENCE_PAT=your_api_token
CONFLUENCE_SPACE_KEY=DS
CONFLUENCE_PARENT_TITLE=Home
python confluence_automation.pyfrom flow import create_qa_flow

# Example main function
# Please replace this with your own main function
def main():
    shared = {
        "question": "In one sentence, what's the end of universe?",
        "answer": None
    }

    qa_flow = create_qa_flow()
    qa_flow.run(shared)
    print("Question:", shared["question"])
    print("Answer:", shared["answer"])

if __name__ == "__main__":
    main()
