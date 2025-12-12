import docker
import requests
import json
import time

# --- CONFIGURATION ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
DOCKER_IMAGE = "python:3.10-slim"  # Lightweight Linux for testing

class AgentZero:
    def __init__(self):
        print(f"[-] Initializing Docker Client...")
        self.d_client = docker.from_env()
        print(f"[-] connecting to Local Brain ({MODEL_NAME})...")
        
    def think(self, prompt):
        """Send a prompt to the local Ollama model (System 1)"""
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2} # Low temp for logic
        }
        try:
            response = requests.post(OLLAMA_URL, json=payload)
            return response.json()['response']
        except Exception as e:
            print(f"Error talking to Ollama: {e}")
            return ""

    def run_simulation(self):
        """
        Creates a Docker container, injects a BUGGY script, and asks AI to fix it.
        """
        print("\n🚀 STARTING SIMULATION")
        
        # 1. The Challenge: A buggy calculator script
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

        # Start the container
        print("[-] Spinning up Sandbox Container...")
        container = self.d_client.containers.run(
            DOCKER_IMAGE, 
            command="tail -f /dev/null", # Keep it alive
            detach=True
        )

        try:
            # Inject buggy code
            print("[-] Injecting Buggy Code...")
            exec_res = container.exec_run(
                f"sh -c 'echo \"{buggy_code}\" > /broken.py'"
            )
            
            # --- THE REASONING LOOP ---
            solved = False
            attempts = 0
            max_attempts = 3
            
            while not solved and attempts < max_attempts:
                attempts += 1
                print(f"\n--- Attempt {attempts}/{max_attempts} ---")
                
                # A. Run the Code (Observe State)
                run_result = container.exec_run("python3 /broken.py")
                output = run_result.output.decode('utf-8')
                exit_code = run_result.exit_code
                
                print(f"   [Observation]: Execution returned code {exit_code}")
                print(f"   [Logs]: {output.strip()}")
                
                if exit_code == 0:
                    print("\n✅ SUCCESS! The agent fixed the code.")
                    solved = True
                    break
                
                # B. Think (Generate Patch)
                print("   [Thinking]: Analyzing error...")
                prompt = f"""
                You are an autonomous AI software engineer.
                You have a python file '/broken.py' that is failing tests.
                
                CURRENT CODE:
                {buggy_code}
                
                ERROR LOGS:
                {output}
                
                TASK: Write the CORRECT python code to fix this bug. 
                Return ONLY the full corrected Python code. Do not use Markdown.
                """
                
                solution_code = self.think(prompt)
                
                # Clean up response (Ollama sometimes adds markdown ```)
                solution_code = solution_code.replace("```python", "").replace("```", "").strip()
                
                print(f"   [Action]: Applying Patch (Length: {len(solution_code)} chars)...")
                
                # C. Apply Patch (Act)
                # Escape quotes for shell command
                safe_code = solution_code.replace('"', '\\"')
                container.exec_run(f"sh -c 'echo \"{solution_code}\" > /broken.py'")
                
                # Update our local view of the code for the next prompt loop
                buggy_code = solution_code

            if not solved:
                print("\n❌ FAILED. Agent could not fix the bug in 3 attempts.")
                
        finally:
            print("[-] Cleaning up Docker Container...")
            container.kill()
            container.remove()

if __name__ == "__main__":
    agent = AgentZero()
    agent.run_simulation()
