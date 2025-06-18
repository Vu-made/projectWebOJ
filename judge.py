import subprocess
import uuid
import os
import tempfile
import shutil
import json

def judge_code(code, lang, config_json_str):
    try:
        config = config_json_str
    except Exception as e:
        return json.dumps({"status": "SE", "error": "Invalid JSON format", "detail": str(e)})

    tests = config.get("tests", {})
    time_limit = int(config.get("time_limit", 1))
    point_per_test = float(config.get("point", 1))

    uid = str(uuid.uuid4())
    folder = os.path.join(tempfile.gettempdir(), uid)
    os.makedirs(folder, exist_ok=True)

    try:
        if lang == "c_cpp":
            source_file = os.path.join(folder, "main.cpp")
            with open(source_file, "w") as f:
                f.write(code)
            image = "code-judge-cpp"
            compile_cmd = "g++ main.cpp -o main"
            run_cmd = "./main"
        elif lang == "python":
            source_file = os.path.join(folder, "main.py")
            with open(source_file, "w") as f:
                f.write(code)
            image = "code-judge-python"
            compile_cmd = ""
            run_cmd = "python3 main.py"
        else:
            return json.dumps({"status": "SE", "error": "Unsupported language"})

        if compile_cmd:
            compile_result = subprocess.run([
                "docker", "run", "--rm",
                "-v", f"{folder}:/app",
                "-w", "/app",
                image,
                "bash", "-c", compile_cmd
            ], capture_output=True)

            if compile_result.returncode != 0:
                return json.dumps({
                    "status": "CE",
                    "error": "Compilation Error",
                    "message": compile_result.stderr.decode()
                })

        results = []
        passed = 0

        for test_id, test_case in tests.items():
            input_data = test_case.get("input", "")
            expected_output = test_case.get("output", "").strip()

            input_file = f"input_{test_id}.txt"
            output_file = f"output_{test_id}.txt"
            time_file = f"time_{test_id}.txt"

            input_path = os.path.join(folder, input_file)
            output_path = os.path.join(folder, output_file)
            time_path = os.path.join(folder, time_file)

            with open(input_path, "w") as f:
                f.write(input_data)

            docker_cmd = [
                "docker", "run", "--rm", "--memory=128m",
                "-v", f"{folder}:/app",
                "-w", "/app",
                image,
                "bash", "-c", f"/usr/bin/time -o {time_file} -f '%e %M' {run_cmd} < {input_file} > {output_file}"
            ]

            test_result = {
                "name": test_id,
                "status": "SE",
                "time": "N/A",
                "memory": "N/A"
            }

            try:
                subprocess.run(docker_cmd, timeout=time_limit, check=True)

                # Read output
                output = ""
                if os.path.exists(output_path):
                    with open(output_path) as f:
                        output = f.read().strip()

                # Get time and memory
                if os.path.exists(time_path):
                    with open(time_path) as tf:
                        timing = tf.read().strip().split()
                        if len(timing) == 2:
                            test_result["time"] = f"{float(timing[0]):.2f}"
                            test_result["memory"] = f"{timing[1]}kb"

                if output == expected_output:
                    test_result["status"] = "AC"
                    passed += 1
                else:
                    test_result["status"] = "WA"

            except subprocess.TimeoutExpired:
                test_result["status"] = "TLE"
            except subprocess.CalledProcessError:
                test_result["status"] = "RE"
            except Exception as e:
                test_result["status"] = "SE"
                test_result["error"] = str(e)

            results.append(test_result)

        return json.dumps(results, indent=2)

    finally:
        shutil.rmtree(folder, ignore_errors=True)
