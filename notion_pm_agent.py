import os
import subprocess
import time
import hashlib

# Your Notion Page ID
PAGE_ID = "395ffebbd15180919936c13f80202395"
PROCESSED_LOG = "pm_processed.log"

# The Workforce: A list of models/agents and their specific jobs.
# You can change the models or prompts here!
WORKFORCE = [
    {
        "role": "Planner (Claude 3.5 Sonnet)",
        "command": 'claude -m "claude-3-5-sonnet" -p "Briefly plan how to execute this task: {task}. Output only the plan."'
    },
    {
        "role": "Coder (Gemini 2.5 Pro)",
        "command": 'claude -m "gemini-2.5-pro" -p "Task: {task}. Based on the following plan, write or edit the necessary code in the current directory.\\n\\nPlan:\\n{previous_output}"'
    },
    {
        "role": "Reviewer (Qwen or Local Model)",
        "command": 'claude -p "Task: {task}. Review the following code changes made to satisfy the task. Ensure they are secure and meet the task requirements. Output a short summary.\\n\\nCoder Output:\\n{previous_output}"'
    }
]

def get_notion_page():
    result = subprocess.run(['ntn', 'pages', 'get', PAGE_ID], capture_output=True, text=True)
    return result.stdout

def update_notion_page(content):
    # Grab the current page content
    current = get_notion_page()
    # Append our new report to the bottom
    new_content = current + "\n\n---\n" + content
    
    # Write to a temp file and push back to Notion
    with open("temp_update.md", "w") as f:
        f.write(new_content)
    
    with open("temp_update.md", "r") as f:
        subprocess.run(['ntn', 'pages', 'edit', PAGE_ID], stdin=f)

def get_new_requests(content):
    """
    Looks for lines in Notion that start with 'REQUEST:'
    Example: REQUEST: Fix the youtube projector alignment.
    """
    requests = []
    for line in content.split('\n'):
        if line.startswith("REQUEST:"):
            req = line.replace("REQUEST:", "").strip()
            req_hash = hashlib.md5(req.encode()).hexdigest()
            requests.append((req_hash, req))
    return requests

def is_processed(req_hash):
    if not os.path.exists(PROCESSED_LOG):
        return False
    with open(PROCESSED_LOG, "r") as f:
        return req_hash in f.read()

def mark_processed(req_hash):
    with open(PROCESSED_LOG, "a") as f:
        f.write(req_hash + "\n")

def run_workforce(task):
    import shlex
    report = f"### PM Report for: {task}\n"
    
    previous_output = ""
    # 1. Read from the workforce list and provide works to each model sequentially
    for worker in WORKFORCE:
        print(f"\n[+] Assigning task to {worker['role']}...")
        
        # Create a safe command line to avoid injection
        prompt = worker["command"].split('-p ')[1].strip('"').format(task=task, previous_output=previous_output)
        model_part = worker["command"].split(' -p')[0]
        
        cmd = f'{model_part} -p {shlex.quote(prompt)}'
        
        # We run the agent CLI and capture what they return
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        # 2. Check what they returned and append to our report
        agent_output = result.stdout.strip()
        if not agent_output:
            agent_output = result.stderr.strip()
            
        print(f"[-] {worker['role']} finished.")
        
        report += f"**{worker['role']} Result:**\n```text\n{agent_output}\n```\n\n"
        previous_output = agent_output
    
    return report

def main():
    print("Notion PM Agent started. Polling every 60 seconds...")
    print("To trigger me, write a line in your Notion page starting with 'REQUEST: '")
    
    while True:
        try:
            page_content = get_notion_page()
            requests = get_new_requests(page_content)
            
            for req_hash, task in requests:
                if not is_processed(req_hash):
                    print(f"\n======================================")
                    print(f"New request found in Notion: {task}")
                    print(f"======================================")
                    
                    # Dispatch to the multi-model workforce
                    report = run_workforce(task)
                    
                    print("\n[+] Updating Notion with the final report...")
                    update_notion_page(report)
                    mark_processed(req_hash)
                    print("[+] Done. Back to polling.")
                    
        except Exception as e:
            print(f"Error occurred: {e}")
            
        time.sleep(60)

if __name__ == "__main__":
    main()
