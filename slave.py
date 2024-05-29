import socketio
import json
import subprocess
import threading
import psutil
import platform
from datetime import datetime
#import pyufw as ufw
import argparse
import requests

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

sio = socketio.Client()

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

    sio.wait()
