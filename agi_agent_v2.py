import docker
import requests
import json
import base64
import time

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
DOCKER_IMAGE = "python:3.10-slim" 

class AgentZero:
    def __init__(self):
        print(f"[-] Initializing Docker Client...")
        self.d_client = docker.from_env()
        print(f"[-] Connecting to Local Brain ({MODEL_NAME})...")
        
    def think(self, prompt):
        """Send a prompt to the local Ollama model"""
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0} # Absolute logic, no creativity
        }
        try:
            print("   [Brain]: Thinking...")
            response = requests.post(OLLAMA_URL, json=payload)
            return response.json()['response']
        except Exception as e:
            print(f"Error talking to Ollama: {e}")
            return ""

    def write_to_container(self, container, filepath, content):
        """
        BULLETPROOF WRITE: Encodes content to Base64 before sending to Docker.
        This prevents shell quote escaping issues (The 'Telephone Game' bug).
        """
        b64_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        # We use python inside the container to decode and write the file
        cmd = f"python3 -c \"import base64; open('{filepath}', 'w').write(base64.b64decode('{b64_content}').decode('utf-8'))\""
        container.exec_run(cmd)

    def run_simulation(self):
        print("\n🚀 STARTING SIMULATION v2.0 (Base64 Transport)")
        
        # 1. The Challenge: A buggy calculator
        buggy_code = """
def divide_numbers(a, b):
    # TODO: This function has a bug.
    return a * b  # INTENTIONAL BUG: Multiplication instead of division

if __name__ == "__main__":
    result = divide_numbers(10, 2)
    expected = 5.0
    if result != expected:
        print(f"FAIL: Expected {expected}, got {result}")
        exit(1)
    else:
        print("SUCCESS: Test Passed!")
        """

        print("[-] Spinning up Sandbox Container...")
        container = self.d_client.containers.run(DOCKER_IMAGE, command="tail -f /dev/null", detach=True)

        try:
            # Inject buggy code using the new safe method
            print("[-] Injecting Buggy Code...")
            self.write_to_container(container, "/broken.py", buggy_code)
            
            solved = False
            attempts = 0
            
            while not solved and attempts < 3:
                attempts += 1
                print(f"\n--- Attempt {attempts}/3 ---")
                
                # A. Run Code
                run_result = container.exec_run("python3 /broken.py")
                output = run_result.output.decode('utf-8')
                exit_code = run_result.exit_code
                
                print(f"   [Observation]: Exit Code {exit_code}")
                print(f"   [Logs]: {output.strip()}")
                
                if exit_code == 0:
                    print("\n✅ SUCCESS! The agent fixed the code.")
                    solved = True
                    break
                
                # B. Think
                prompt = f"""
                You are an expert python debugger.
                The file '/broken.py' is failing.

                CODE:
                {buggy_code}

                ERROR OUTPUT:
                {output}

                TASK: Return the FIXED code.
                RULES:
                1. Fix the logic error.
                2. Return ONLY the python code.
                3. Do not add markdown backticks (```).
                4. Keep the print statements exactly as they are.
                """
                
                solution_code = self.think(prompt)
                
                # Cleanup: remove markdown if the model ignores instruction
                solution_code = solution_code.replace("```python", "").replace("```", "").strip()
                
                # C. Act (Safely)
                print(f"   [Action]: Applying Patch via Base64...")
                self.write_to_container(container, "/broken.py", solution_code)
                
                # Update local memory
                buggy_code = solution_code

            if not solved:
                print("\n❌ FAILED after 3 attempts.")
                
        finally:
            print("[-] Cleaning up...")
            container.kill()
            container.remove()

if __name__ == "__main__":
    agent = AgentZero()
    agent.run_simulation()
