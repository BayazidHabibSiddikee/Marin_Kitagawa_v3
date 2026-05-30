from  import MasterAgent

def run_deep_audit():
    # We use gemini as the primary reasoner to coordinate the other CLIs
    agent = MasterAgent(default_agent='gemini') 
    
    task = (
        "Perform a deep project audit. "
        "1. Use kiro-cli to check for any abnormal file permissions or missing dependencies. "
        "2. Use opencode to scan for logical bugs in the tool execution flow (check for any remaining DEVNULL blocks). "
        "3. Use gemini to analyze the overall architecture and suggest stability improvements. "
        "4. Fix any found errors immediately using opencode. "
        "Continue the loop for at least 10 cycles of reasoning to ensure total project health."
    )
    
    print("Starting autonomous audit loop...")
    print(f"Task: {task}\n")
    
    result = agent.execute_task(task)
    print(f"\n--- FINAL AUDIT RESULT ---\n{result}")

if __name__ == '__main__':
    run_deep_audit()
