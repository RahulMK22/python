import docker
import requests
import base64
import time
import re

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
DOCKER_IMAGE = "python:3.10-slim" 

class AgentExplorer:
    def __init__(self):
        self.d_client = docker.from_env()
        print(f"[-] Connected to Brain ({MODEL_NAME})")

    def think(self, context, task):
        """
        System 2 Thinking: The agent decides WHICH tool to use next.
        """
        prompt = f"""
        You are an autonomous developer debugging a repository.
        
        TASK: {task}
        
        CURRENT CONTEXT:
        {context}
        
        AVAILABLE TOOLS:
        1. LIST_FILES <dir_path>  (Example: LIST_FILES src/)
        2. READ_FILE <file_path>  (Example: READ_FILE src/utils.py)
        3. WRITE_FILE <file_path> (Overwrites file with code)
        4. RUN_TEST               (Runs the test suite)

        INSTRUCTIONS:
        - You cannot see the whole codebase at once. You must explore.
        - If you see an import error or logic error, read the imported file.
        - To use a tool, start your response with the command.
        
        EXAMPLE RESPONSE 1:
        LIST_FILES src/

        EXAMPLE RESPONSE 2:
        READ_FILE src/math_lib.py
        
        EXAMPLE RESPONSE 3 (Fixing the bug):
        WRITE_FILE src/math_lib.py
        def add(a, b):
            return a + b
        
        What is your next move?
        """
        
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_ctx": 4096}
        }
        try:
            resp = requests.post(OLLAMA_URL, json=payload).json()['response']
            return resp.strip()
        except Exception as e:
            return f"ERROR: {e}"

    def write_to_container(self, container, filepath, content):
        b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        cmd = f"python3 -c \"import base64, os; os.makedirs(os.path.dirname('{filepath}'), exist_ok=True); open('{filepath}', 'w').write(base64.b64decode('{b64}').decode('utf-8'))\""
        container.exec_run(cmd)

    def run_simulation(self):
        print("\n🚀 STARTING SIMULATION v3.0 (The Explorer)")
        
        # 1. Setup a Multi-File Project (The "Mini-Repo")
        # Structure:
        #   /app/main.py   (The entry point)
        #   /app/utils.py  (The broken dependency)
        
        main_code = """
from utils import calculate_price

def test_cart():
    # We expect 2 items at $10 each = $20
    total = calculate_price(10, 2)
    if total != 20:
        print(f"FAIL: Expected 20, got {total}")
        exit(1)
    else:
        print("SUCCESS: Cart total is correct.")

if __name__ == "__main__":
    test_cart()
"""
        # The Bug is here: It subtracts instead of adds!
        utils_code = """
def calculate_price(price, quantity):
    # TODO: Implement pricing logic
    return price - quantity  # BUG: Should be multiply!
"""

        print("[-] Creating Virtual Environment...")
        container = self.d_client.containers.run(DOCKER_IMAGE, command="tail -f /dev/null", detach=True)
        
        try:
            # Create the files inside Docker
            self.write_to_container(container, "/app/main.py", main_code)
            self.write_to_container(container, "/app/utils.py", utils_code)
            
            # --- THE LOOP ---
            history = []
            solved = False
            
            print("[-] Agent started. Goal: Fix the test failure.")
            
            for step in range(1, 10): # Max 10 steps
                print(f"\n--- STEP {step} ---")
                
                # Context Management
                context_str = "\n".join(history[-3:]) # Only keep last 3 actions in memory
                
                # Decision Time
                action = self.think(context_str, "Run tests, locate the bug in the files, and fix it.")
                
                print(f"🤖 AGENT SAYS: {action.splitlines()[0]} ...") # Print first line only
                
                # Parsing the Action
                if "RUN_TEST" in action:
                    res = container.exec_run("python3 /app/main.py")
                    output = res.output.decode('utf-8').strip()
                    exit_code = res.exit_code
                    print(f"   [System]: Test Output -> {output}")
                    history.append(f"Action: RUN_TEST\nResult: {output}")
                    
                    if exit_code == 0 and "SUCCESS" in output:
                        print("\n🎉 VICTORY! The agent navigated the file system and fixed the bug.")
                        solved = True
                        break
                        
                elif "LIST_FILES" in action:
                    target_dir = action.split(" ")[1] if len(action.split(" ")) > 1 else "."
                    res = container.exec_run(f"ls -R {target_dir}")
                    output = res.output.decode('utf-8').strip()
                    print(f"   [System]: Files -> {output}")
                    history.append(f"Action: LIST_FILES {target_dir}\nResult: {output}")

                elif "READ_FILE" in action:
                    # Extract filename
                    match = re.search(r"READ_FILE\s+(\S+)", action)
                    if match:
                        filename = match.group(1)
                        print(f"   [System]: Reading {filename}...")
                        res = container.exec_run(f"cat {filename}")
                        content = res.output.decode('utf-8')
                        history.append(f"Action: READ_FILE {filename}\nContent:\n{content}")
                    else:
                        print("   [System]: Error - No filename specified")

                elif "WRITE_FILE" in action:
                    # Extract filename and code
                    match = re.search(r"WRITE_FILE\s+(\S+)", action)
                    if match:
                        filename = match.group(1)
                        # Assume the rest of the response is the code
                        code = action.split(filename)[1].strip()
                        # Clean code block format
                        code = code.replace("```python", "").replace("```", "").strip()
                        
                        print(f"   [System]: Writing patch to {filename}...")
                        self.write_to_container(container, filename, code)
                        history.append(f"Action: WROTE_FILE {filename}")
                        
                        # Auto-trigger test after write
                        print("   [System]: Auto-running verification...")
                        res = container.exec_run("python3 /app/main.py")
                        if res.exit_code == 0:
                            print(f"   [System]: {res.output.decode('utf-8').strip()}")
                            print("\n🎉 VICTORY! Bug fixed.")
                            solved = True
                            break
                    else:
                        print("   [System]: Error parsing WRITE command")

            if not solved:
                print("\n❌ DEFEAT. Agent got lost in the file system.")

        finally:
            container.kill()
            container.remove()

if __name__ == "__main__":
    agent = AgentExplorer()
    agent.run_simulation()
