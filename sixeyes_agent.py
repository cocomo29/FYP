import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from urllib.parse import unquote
import socketio
import json
import subprocess
import threading
import psutil
import platform
from datetime import datetime
import argparse
import requests

# Flask app and CORS setup
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Define the base directory to manage
BASE_DIR = '/'

def list_files(directory):
    files = []
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path):
            files.append({'name': filename, 'type': 'file'})
        elif os.path.isdir(file_path):
            files.append({'name': filename + '/', 'type': 'directory'})
    return files

def get_file_content(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

@app.route('/')
def file_explorer():
    path = request.args.get('path', '')
    full_path = os.path.join(BASE_DIR, path)

    if not os.path.exists(full_path):
        return jsonify({'error': f'Path does not exist: {path}'}), 404

    files = list_files(full_path)
    return jsonify({'files': files, 'current_path': path})

@app.route('/upload', methods=['POST'])
def upload_file():
    path = request.form['path']
    upload_dir = os.path.join(BASE_DIR, path)

    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            filename = os.path.join(upload_dir, file.filename)
            file.save(filename)
            return jsonify({'message': 'File uploaded successfully'}), 200

    return jsonify({'error': 'No file uploaded'}), 400

@app.route('/delete', methods=['POST'])
def delete_file():
    data = request.get_json()
    path = data.get('path')
    filename = data.get('filename')
    file_path = os.path.join(BASE_DIR, path, filename)

    if os.path.exists(file_path):
        if os.path.isdir(file_path):
            os.rmdir(file_path)
        else:
            os.remove(file_path)
        return jsonify({'message': 'File deleted successfully'}), 200
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/rename', methods=['POST'])
def rename_file():
    data = request.get_json()
    path = data.get('path', '')
    old_name = data.get('old_name', '')
    new_name = data.get('new_name', '')

    old_path = os.path.join(BASE_DIR, path, old_name)
    new_path = os.path.join(BASE_DIR, path, new_name)

    if os.path.exists(old_path):
        os.rename(old_path, new_path)
        return jsonify({'message': 'File renamed successfully'}), 200
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/create_file', methods=['POST'])
def create_file():
    data = request.get_json()
    path = data.get('path')
    file_name = data.get('file_name')
    file_content = data.get('file_content')
    file_path = os.path.join(BASE_DIR, path, file_name)

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
        return jsonify({'message': 'File created successfully'}), 200
    except Exception as err:
        return jsonify({'error': str(err)}), 500

@app.route('/get_content', methods=['POST'])
def get_file_content_api():
    print(request.json)  # Debugging: Print request JSON data
    data = request.get_json()
    path = data.get('path')
    filename = data.get('filename')
    file_path = os.path.join(BASE_DIR, path, filename)

    if os.path.exists(file_path):
        content = get_file_content(file_path)
        return jsonify({'content': content}), 200
    else:
        return jsonify({'error': 'File not found'}), 404

@app.route('/download/<path:file_path>', methods=['GET'])
def download_file(file_path):
    try:
        # Decode the file path
        decoded_file_path = unquote(file_path)

        # Construct the absolute file path
        absolute_file_path = os.path.normpath(os.path.join(BASE_DIR, decoded_file_path))
        # print(absolute_file_path)
        # Check if the resolved absolute path is within the allowed directory (BASE_DIR)
        if not absolute_file_path.startswith(BASE_DIR):
            return jsonify({'error': 'Invalid file path or unauthorized access'}), 403

        # Check if the file exists and is a regular file
        if not os.path.isfile(absolute_file_path):
            return jsonify({'error': 'File not found or invalid path'}), 404

        # Serve the file for download
        # print(decoded_file_path.split(BASE_DIR)[0],decoded_file_path.split(BASE_DIR)[1])
        return send_from_directory(os.path.dirname(absolute_file_path), os.path.basename(absolute_file_path), as_attachment=True)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# SocketIO client setup
sio = socketio.Client()

def get_public_ip():
    """Fetch the public IP address of the agent."""
    try:
        response = requests.get('https://ipinfo.io/ip')
        public_ip = response.text.strip()
        return public_ip
    except requests.RequestException as e:
        print(f"Error getting public IP: {e}")
        return None

def get_size(bytes, suffix="B"):
    """Convert bytes to a more suitable unit and format."""
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_system_info():
    """Collects detailed system, CPU, and memory information into a dictionary."""
    system_info = {}

    # System Information
    uname = platform.uname()
    system_info['System'] = uname.system
    system_info['NodeName'] = uname.node
    system_info['Release'] = uname.release
    system_info['Version'] = uname.version
    system_info['Machine'] = uname.machine
    system_info['Processor'] = uname.processor
    system_info['PublicIP'] = get_public_ip()
    
    # Boot Time
    boot_time_timestamp = psutil.boot_time()
    bt = datetime.fromtimestamp(boot_time_timestamp)
    system_info['BootTime'] = f"{bt.year}/{bt.month}/{bt.day} {bt.hour}:{bt.minute}:{bt.second}"
    
    # CPU Information
    system_info['PhysicalCores'] = psutil.cpu_count(logical=False)
    system_info['TotalCores'] = psutil.cpu_count(logical=True)
    cpufreq = psutil.cpu_freq()
    system_info['MaxFrequency'] = f"{cpufreq.max:.2f}Mhz"
    system_info['MinFrequency'] = f"{cpufreq.min:.2f}Mhz"
    system_info['CurrentFrequency'] = f"{cpufreq.current:.2f}Mhz"
    
    cpu_usage_per_core = {}
    for i, percentage in enumerate(psutil.cpu_percent(percpu=True, interval=1)):
        cpu_usage_per_core[f"Core_{i}"] = f"{percentage}"
    system_info['CPUUsagePerCore'] = cpu_usage_per_core
    system_info['TotalCPUUsage'] = f"{psutil.cpu_percent()}"
    
    # Memory Information
    memory_info = {}
    svmem = psutil.virtual_memory()
    memory_info['Total'] = get_size(svmem.total)
    memory_info['Available'] = get_size(svmem.available)
    memory_info['Used'] = get_size(svmem.used)
    memory_info['Percentage'] = f"{svmem.percent}"
    system_info['MemoryInformation'] = memory_info
    
    swap_info = {}
    swap = psutil.swap_memory()
    swap_info['Total'] = get_size(swap.total)
    swap_info['Free'] = get_size(swap.free)
    swap_info['Used'] = get_size(swap.used)
    swap_info['Percentage'] = f"{swap.percent}"
    system_info['Swap'] = swap_info

    return system_info

def send_system_info():
    while True:
        data = get_system_info()
        sio.emit('system_info', json.dumps(data))
        sio.sleep(1)

@sio.event
def command(data):
    print(data)
    try:
        result = subprocess.check_output(str(data), shell=True)
        print(result)
        sio.emit('command_result', json.dumps({'result': result.decode('utf-8'), 'data': data}))
    except Exception as e:
        print(e)
        sio.emit('command_result', json.dumps({'error': str(e)}))

def get_service_info(service_name):
    try:
        output_active = subprocess.check_output(["systemctl", "is-active", service_name])
        active_status = output_active.strip().decode() == "active"

        output_enabled = subprocess.check_output(["systemctl", "is-enabled", service_name])
        enabled_status = output_enabled.strip().decode() == "enabled"

        return {"name": service_name, "installed": enabled_status, "status": "running" if active_status else "stopped"}
    except subprocess.CalledProcessError:
        return {"name": service_name, "installed": False, "status": "stopped"}

@sio.event
def get_service_status():
    services = [
        get_service_info("apache2"),
        get_service_info("nginx"),
        get_service_info("redis"),
        get_service_info("openssh"),
        get_service_info("cmatrix")
    ]
    sio.emit("get_service_status_result", services)

@sio.event
def get_ports_event():
    result = ufw.status()
    sio.emit("ports_info", json.dumps({"result": result}))

@sio.event
def install_service(service_name):
    try:
        result = f"Installing {service_name}..."
        print(result)
        install_command = f"sudo apt install {service_name} -y"
        output = subprocess.check_output(install_command, shell=True, stderr=subprocess.STDOUT)
        output_str = output.decode('utf-8').strip()
        print(output_str)
        sio.emit('install_service_result', json.dumps({'result': output_str, 'service_name': service_name}))
    except subprocess.CalledProcessError as e:
        print(e.output.decode('utf-8').strip())
        sio.emit('install_service_result', json.dumps({'error': e.output.decode('utf-8').strip()}))

@sio.event
def uninstall_service(service_name):
    try:
        result = f"Uninstalling {service_name}..."
        print(result)
        uninstall_command = f"sudo apt remove {service_name} -y"
        output = subprocess.check_output(uninstall_command, shell=True, stderr=subprocess.STDOUT)
        output_str = output.decode('utf-8').strip()
        print(output_str)
        sio.emit('uninstall_service_result', json.dumps({'result': output_str, 'service_name': service_name}))
    except subprocess.CalledProcessError as e:
        print(e.output.decode('utf-8').strip())
        sio.emit('uninstall_service_result', json.dumps({'error': e.output.decode('utf-8').strip()}))

@sio.event
def start_service(service_name):
    try:
        result = f"Starting {service_name}..."
        print(result)
        start_command = f"sudo systemctl start {service_name}"
        output = subprocess.check_output(start_command, shell=True, stderr=subprocess.STDOUT)
        output_str = output.decode('utf-8').strip()
        print(output_str)
        sio.emit('start_service_result', json.dumps({'result': output_str, 'service_name': service_name}))
    except subprocess.CalledProcessError as e:
        print(e.output.decode('utf-8').strip())
        sio.emit('start_service_result', json.dumps({'error': e.output.decode('utf-8').strip()}))

@sio.event
def stop_service(service_name):
    try:
        result = f"Stopping {service_name}..."
        print(result)
        stop_command = f"sudo systemctl stop {service_name}"
        output = subprocess.check_output(stop_command, shell=True, stderr=subprocess.STDOUT)
        output_str = output.decode('utf-8').strip()
        print(output_str)
        sio.emit('stop_service_result', json.dumps({'result': output_str, 'service_name': service_name}))
    except subprocess.CalledProcessError as e:
        print(e.output.decode('utf-8').strip())
        sio.emit('stop_service_result', json.dumps({'error': e.output.decode('utf-8').strip()}))

@sio.event
def restart_service(service_name):
    try:
        result = f"Restarting {service_name}..."
        print(result)
        restart_command = f"sudo systemctl restart {service_name}"
        output = subprocess.check_output(restart_command, shell=True, stderr=subprocess.STDOUT)
        output_str = output.decode('utf-8').strip()
        print(output_str)
        sio.emit('restart_service_result', json.dumps({'result': output_str, 'service_name': service_name}))
    except subprocess.CalledProcessError as e:
        print(e.output.decode('utf-8').strip())
        sio.emit('restart_service_result', json.dumps({'error': e.output.decode('utf-8').strip()}))

@sio.event
def connect():
    public_ip = get_public_ip()
    if public_ip:
        sio.emit('agent_details', json.dumps({'public_ip': public_ip, 'agent_name': agent_name}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SocketIO Client')
    parser.add_argument('master_ip', type=str, help='Master IP address')
    parser.add_argument('agent_name', type=str, help='Agent name')
    args = parser.parse_args()

    master_ip = args.master_ip
    agent_name = args.agent_name

    sio.connect(f'http://{master_ip}:5000')
    threading.Thread(target=send_system_info).start()

    # Run Flask app
    app.run(host='0.0.0.0', port=5002)

    sio.wait()
