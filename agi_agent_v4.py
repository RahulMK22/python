import docker
import requests
import base64
import json
import re

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
DOCKER_IMAGE = "python:3.10-slim" 

class AgentJSON:
    def __init__(self):
        self.d_client = docker.from_env()
        print(f"[-] Connected to Brain ({MODEL_NAME}) - JSON MODE ACTIVE")

    def think(self, history):
        """
        Forces the LLM to output valid JSON only.
        """
        prompt = f"""
        You are a robotic software engineer. You interact with a file system via JSON commands.
        
        GOAL: Fix the failing test in /app/main.py.
        CURRENT WORKING DIR: /app
        
        API SCHEMA:
        1. List files:  {{"action": "list_files", "path": "."}}
        2. Read file:   {{"action": "read_file", "path": "filename.py"}}
        3. Write file:  {{"action": "write_file", "path": "filename.py", "content": "code_here"}}
        4. Run tests:   {{"action": "run_test", "cmd": "python3 /app/main.py"}}

        HISTORY:
        {json.dumps(history, indent=2)}

        INSTRUCTIONS:
        - Analyze the history. Determine the next logical step.
        - The bug is likely in a dependency, not the test file itself.
        - RETURN ONLY JSON. NO TEXT. NO MARKDOWN.
        """
        
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # FORCE OLLAMA TO USE JSON MODE
            "options": {"temperature": 0.0}
        }
        
        try:
            resp = requests.post(OLLAMA_URL, json=payload).json()['response']
            return json.loads(resp) # Parse immediately to verify validity
        except Exception as e:
            print(f"   [Brain Error]: Generated invalid JSON. Retrying... {e}")
            return None

    def write_to_container(self, container, filepath, content):
        b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        cmd = f"python3 -c \"import base64, os; os.makedirs(os.path.dirname('{filepath}'), exist_ok=True); open('{filepath}', 'w').write(base64.b64decode('{b64}').decode('utf-8'))\""
        container.exec_run(cmd)

    def run_simulation(self):
        print("\n🚀 STARTING SIMULATION v4.0 (JSON Control Loop)")
        
        # Setup Multi-File Project
        main_code = """
from utils import calculate_price
if __name__ == "__main__":
    total = calculate_price(10, 2)
    if total != 20:
        print(f"FAIL: Expected 20, got {total}")
        exit(1)
    print("SUCCESS: Cart total is correct.")
"""
        utils_code = """
def calculate_price(price, quantity):
    return price - quantity  # BUG
"""

        container = self.d_client.containers.run(DOCKER_IMAGE, command="tail -f /dev/null", detach=True)
        
        try:
            # Initialize Environment
            self.write_to_container(container, "/app/main.py", main_code)
            self.write_to_container(container, "/app/utils.py", utils_code)
            
            history = [{"role": "system", "content": "Environment started. Tests are failing."}]
            solved = False
            
            for step in range(1, 10):
                print(f"\n--- STEP {step} ---")
                
                # 1. THINK
                decision = self.think(history[-4:]) # Keep context short
                if not decision: continue # Skip if JSON failed
                
                print(f"🤖 DECISION: {decision['action']} -> {decision.get('path', '')}")
                
                # 2. ACT
                action = decision.get("action")
                result = ""
                
                if action == "run_test":
                    res = container.exec_run("python3 /app/main.py")
                    result = res.output.decode('utf-8').strip()
                    exit_code = res.exit_code
                    print(f"   [Output]: {result}")
                    
                    if exit_code == 0 and "SUCCESS" in result:
                        print("\n🎉 VICTORY! The JSON Agent solved the problem.")
                        solved = True
                        break
                
                elif action == "list_files":
                    path = decision.get("path", ".")
                    res = container.exec_run(f"ls -R {path}")
                    result = res.output.decode('utf-8').strip()
                    print(f"   [Output]: \n{result}")

                elif action == "read_file":
                    path = decision.get("path")
                    res = container.exec_run(f"cat {path}")
                    result = res.output.decode('utf-8')
                    print(f"   [Output]: (Read {len(result)} chars)")

                elif action == "write_file":
                    path = decision.get("path")
                    content = decision.get("content")
                    print(f"   [Action]: Overwriting {path}...")
                    self.write_to_container(container, path, content)
                    result = "File updated successfully."
                    
                    # Heuristic: Immediately verify after writing
                    print("   [Auto-Verify]: Running tests...")
                    res = container.exec_run("python3 /app/main.py")
                    if res.exit_code == 0:
                        print(f"   [Output]: {res.output.decode('utf-8').strip()}")
                        print("\n🎉 VICTORY! Bug fixed during verify.")
                        solved = True
                        break

                # 3. OBSERVE (Update History)
                history.append({"role": "agent", "action": action, "result": result})

            if not solved:
                print("\n❌ DEFEAT. Max steps reached.")

        finally:
            container.kill()
            container.remove()

if __name__ == "__main__":
    agent = AgentJSON()
    agent.run_simulation()
