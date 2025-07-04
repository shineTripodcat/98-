#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import psutil
import platform
from datetime import datetime
from typing import Dict, Any

def setup_logging(log_level=logging.INFO, log_file='logs/app.log'):
    """设置日志配置，并屏蔽 werkzeug 日志"""
    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    
    # 创建日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # 清除现有的处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器
    try:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"日志文件处理器初始化失败: {e}")

    # 屏蔽 werkzeug 日志
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    # 设置第三方库的日志级别
    logging.getLogger('selenium').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('webdriver_manager').setLevel(logging.WARNING)

def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    try:
        # 基本系统信息
        system_info = {
            'platform': platform.platform(),
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'machine': platform.machine(),
            'processor': platform.processor(),
            'python_version': platform.python_version(),
            'hostname': platform.node()
        }
        
        # CPU信息
        cpu_info = {
            'cpu_count': psutil.cpu_count(),
            'cpu_count_logical': psutil.cpu_count(logical=True),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'cpu_freq': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
        }
        
        # 内存信息
        memory = psutil.virtual_memory()
        memory_info = {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent,
            'total_gb': round(memory.total / (1024**3), 2),
            'available_gb': round(memory.available / (1024**3), 2),
            'used_gb': round(memory.used / (1024**3), 2)
        }
        
        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_info = {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': round((disk.used / disk.total) * 100, 2),
            'total_gb': round(disk.total / (1024**3), 2),
            'used_gb': round(disk.used / (1024**3), 2),
            'free_gb': round(disk.free / (1024**3), 2)
        }
        
        # 网络信息
        network = psutil.net_io_counters()
        network_info = {
            'bytes_sent': network.bytes_sent,
            'bytes_recv': network.bytes_recv,
            'packets_sent': network.packets_sent,
            'packets_recv': network.packets_recv
        }
        
        # 进程信息
        current_process = psutil.Process()
        process_info = {
            'pid': current_process.pid,
            'name': current_process.name(),
            'status': current_process.status(),
            'create_time': datetime.fromtimestamp(current_process.create_time()).isoformat(),
            'cpu_percent': current_process.cpu_percent(),
            'memory_info': current_process.memory_info()._asdict(),
            'memory_percent': current_process.memory_percent(),
            'num_threads': current_process.num_threads()
        }
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system': system_info,
            'cpu': cpu_info,
            'memory': memory_info,
            'disk': disk_info,
            'network': network_info,
            'process': process_info
        }
    
    except Exception as e:
        return {
            'error': f"获取系统信息失败: {str(e)}",
            'timestamp': datetime.now().isoformat()
        }

def format_bytes(bytes_value: int) -> str:
    """格式化字节数为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"

def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def validate_url(url: str) -> bool:
    """验证URL格式"""
    import re
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'  # domain...
        r'(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # host...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None

def sanitize_filename(filename: str) -> str:
    """清理文件名，移除非法字符"""
    import re
    # 移除或替换非法字符
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # 移除控制字符
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', filename)
    # 限制长度
    if len(filename) > 255:
        filename = filename[:255]
    return filename.strip()

def ensure_directory(directory: str) -> bool:
    """确保目录存在"""
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"创建目录失败 {directory}: {str(e)}")
        return False

def get_file_size(filepath: str) -> int:
    """获取文件大小"""
    try:
        return os.path.getsize(filepath)
    except:
        return 0

def get_file_modified_time(filepath: str) -> str:
    """获取文件修改时间"""
    try:
        timestamp = os.path.getmtime(filepath)
        return datetime.fromtimestamp(timestamp).isoformat()
    except:
        return ''

def is_port_available(port: int, host: str = 'localhost') -> bool:
    """检查端口是否可用"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0
    except:
        return False

def get_available_port(start_port: int = 5000, max_attempts: int = 100) -> int:
    """获取可用端口"""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port):
            return port
    raise RuntimeError(f"无法找到可用端口 (尝试范围: {start_port}-{start_port + max_attempts})")

def parse_cron_expression(cron_expr: str) -> Dict[str, Any]:
    """解析cron表达式"""
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron表达式必须包含5个部分")
        
        return {
            'minute': parts[0],
            'hour': parts[1],
            'day': parts[2],
            'month': parts[3],
            'day_of_week': parts[4],
            'valid': True
        }
    except Exception as e:
        return {
            'valid': False,
            'error': str(e)
        }

def create_backup_filename(original_filename: str) -> str:
    """创建备份文件名"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    name, ext = os.path.splitext(original_filename)
    return f"{name}_backup_{timestamp}{ext}"

def cleanup_old_files(directory: str, pattern: str = '*.csv', max_age_days: int = 30) -> int:
    """清理旧文件"""
    import glob
    from datetime import timedelta
    
    try:
        pattern_path = os.path.join(directory, pattern)
        files = glob.glob(pattern_path)
        
        cutoff_time = datetime.now() - timedelta(days=max_age_days)
        deleted_count = 0
        
        for file_path in files:
            try:
                file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_time < cutoff_time:
                    os.remove(file_path)
                    deleted_count += 1
                    logging.info(f"删除旧文件: {file_path}")
            except Exception as e:
                logging.error(f"删除文件失败 {file_path}: {str(e)}")
        
        return deleted_count
    
    except Exception as e:
        logging.error(f"清理旧文件失败: {str(e)}")
        return 0

def get_chrome_version() -> str:
    """获取Chrome版本"""
    try:
        import subprocess
        import re
        
        if platform.system() == 'Windows':
            # Windows
            paths = [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe'
            ]
            
            for path in paths:
                if os.path.exists(path):
                    result = subprocess.run([path, '--version'], capture_output=True, text=True)
                    if result.returncode == 0:
                        match = re.search(r'(\d+\.\d+\.\d+\.\d+)', result.stdout)
                        if match:
                            return match.group(1)
        
        elif platform.system() == 'Linux':
            # Linux
            result = subprocess.run(['google-chrome', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
        
        elif platform.system() == 'Darwin':
            # macOS
            result = subprocess.run(['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                match = re.search(r'(\d+\.\d+\.\d+\.\d+)', result.stdout)
                if match:
                    return match.group(1)
        
        return 'Unknown'
    
    except Exception as e:
        logging.debug(f"获取Chrome版本失败: {str(e)}")
        return 'Unknown'

def test_selenium_setup() -> Dict[str, Any]:
    """测试Selenium设置"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from webdriver_manager.chrome import ChromeDriverManager
        
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        service = webdriver.chrome.service.Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # 测试访问页面
        driver.get('https://www.google.com')
        title = driver.title
        driver.quit()
        
        return {
            'success': True,
            'message': 'Selenium设置正常',
            'test_title': title,
            'chrome_version': get_chrome_version()
        }
    
    except Exception as e:
        return {
            'success': False,
            'message': f'Selenium设置失败: {str(e)}',
            'chrome_version': get_chrome_version()
        }