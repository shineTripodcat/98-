#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

def test_basic_connectivity():
    """测试基本网络连接"""
    print("=== 测试基本网络连接 ===")
    
    test_urls = [
        "https://www.baidu.com",
        "https://s9ko.avp76.net",
        "https://httpbin.org/ip"
    ]
    
    for url in test_urls:
        try:
            print(f"测试连接: {url}")
            response = requests.get(url, timeout=10)
            print(f"  状态码: {response.status_code}")
            print(f"  响应时间: {response.elapsed.total_seconds():.2f}秒")
            print(f"  ✓ 连接成功")
        except Exception as e:
            print(f"  ✗ 连接失败: {str(e)}")
        print()

def test_proxy_connection():
    """测试代理连接"""
    print("=== 测试代理连接 ===")
    
    proxy = "http://127.0.0.1:7890"
    proxies = {
        'http': proxy,
        'https': proxy
    }
    
    test_urls = [
        "https://httpbin.org/ip",
        "https://s9ko.avp76.net"
    ]
    
    for url in test_urls:
        try:
            print(f"通过代理测试连接: {url}")
            response = requests.get(url, proxies=proxies, timeout=15)
            print(f"  状态码: {response.status_code}")
            print(f"  响应时间: {response.elapsed.total_seconds():.2f}秒")
            if url == "https://httpbin.org/ip":
                print(f"  IP信息: {response.json()}")
            print(f"  ✓ 代理连接成功")
        except Exception as e:
            print(f"  ✗ 代理连接失败: {str(e)}")
        print()

def create_test_driver():
    """创建测试用的Chrome驱动"""
    options = Options()
    options.add_argument('--headless')
    
    # Docker环境优化选项
    if os.path.exists('/.dockerenv') or os.environ.get('MICRO_ENV'):
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-plugins')
        options.add_argument('--disable-images')
        options.add_argument('--disable-javascript')
        options.add_argument('--disable-css')
        # 网络稳定性选项
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-renderer-backgrounding')
        options.add_argument('--disable-features=TranslateUI')
        options.add_argument('--disable-ipc-flooding-protection')
        options.add_argument('--disable-background-networking')
        options.add_argument('--disable-default-apps')
        options.add_argument('--disable-sync')
        options.add_argument('--aggressive-cache-discard')
        options.add_argument('--max_old_space_size=4096')
        print("已添加Docker环境优化选项")
    
    # 设置代理
    proxy = "http://192.168.50.1:7890"
    options.add_argument(f'--proxy-server={proxy}')
    
    # 设置Chrome路径
    if os.environ.get('CHROME_BIN'):
        options.binary_location = os.environ.get('CHROME_BIN')
        print(f"使用Chrome路径: {os.environ.get('CHROME_BIN')}")
    
    # 设置ChromeDriver路径
    chromedriver_path = None
    if os.environ.get('CHROMEDRIVER_PATH'):
        chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
    elif os.path.exists('/usr/bin/chromedriver'):
        chromedriver_path = '/usr/bin/chromedriver'
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        chromedriver_path = os.path.join(current_dir, 'drivers', 'chromedriver-win64', 'chromedriver.exe')
    
    print(f"使用ChromeDriver路径: {chromedriver_path}")
    
    if not os.path.exists(chromedriver_path):
        raise FileNotFoundError(f"ChromeDriver文件不存在: {chromedriver_path}")
    
    service = webdriver.chrome.service.Service(chromedriver_path)
    driver = webdriver.Chrome(service=service, options=options)
    
    # 设置超时
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(15)
    driver.set_window_size(1920, 1080)
    
    return driver

def test_selenium_connection():
    """测试Selenium连接"""
    print("=== 测试Selenium连接 ===")
    
    driver = None
    try:
        print("创建Chrome驱动...")
        driver = create_test_driver()
        print("✓ Chrome驱动创建成功")
        
        # 测试访问百度
        print("\n测试访问百度...")
        start_time = time.time()
        driver.get("https://www.baidu.com")
        load_time = time.time() - start_time
        print(f"✓ 百度访问成功，加载时间: {load_time:.2f}秒")
        print(f"页面标题: {driver.title}")
        
        # 测试访问目标网站
        print("\n测试访问目标网站...")
        start_time = time.time()
        driver.get("https://s9ko.avp76.net")
        load_time = time.time() - start_time
        print(f"✓ 目标网站访问成功，加载时间: {load_time:.2f}秒")
        print(f"页面标题: {driver.title}")
        
        # 检查页面内容
        page_source = driver.page_source
        if "连接被重置" in page_source or "ERR_CONNECTION_RESET" in page_source:
            print("✗ 页面显示连接被重置错误")
        elif len(page_source) < 1000:
            print(f"⚠ 页面内容较少，可能加载不完整 (长度: {len(page_source)})")
        else:
            print(f"✓ 页面内容正常 (长度: {len(page_source)})")
        
    except TimeoutException as e:
        print(f"✗ 超时错误: {str(e)}")
    except WebDriverException as e:
        print(f"✗ WebDriver错误: {str(e)}")
    except Exception as e:
        print(f"✗ 其他错误: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
                print("Chrome驱动已关闭")
            except:
                pass

def test_forum_page_access():
    """测试论坛页面访问"""
    print("=== 测试论坛页面访问 ===")
    
    driver = None
    try:
        driver = create_test_driver()
        
        # 测试访问论坛首页
        print("访问论坛首页...")
        driver.get("https://s9ko.avp76.net")
        time.sleep(3)
        print(f"首页标题: {driver.title}")
        
        # 测试访问论坛列表页
        forum_url = "https://s9ko.avp76.net/forum.php?mod=forumdisplay&fid=36&filter=typeid&typeid=672&page=1"
        print(f"\n访问论坛列表页: {forum_url}")
        
        start_time = time.time()
        driver.get(forum_url)
        
        # 等待页面加载完成
        WebDriverWait(driver, 30).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        load_time = time.time() - start_time
        
        print(f"✓ 论坛页面访问成功，加载时间: {load_time:.2f}秒")
        print(f"页面标题: {driver.title}")
        
        # 检查是否有TID链接
        page_source = driver.page_source
        import re
        tid_pattern = r'mod=viewthread&(?:amp;)?tid=(\d+)'
        matches = re.findall(tid_pattern, page_source)
        unique_tids = list(set(matches))
        
        print(f"找到 {len(unique_tids)} 个TID")
        if unique_tids:
            print(f"示例TID: {unique_tids[:5]}")
        
    except Exception as e:
        print(f"✗ 论坛页面访问失败: {str(e)}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

def main():
    """主函数"""
    print("网络连接诊断工具")
    print("=" * 50)
    
    # 显示环境信息
    print("环境信息:")
    print(f"  Python版本: {sys.version}")
    print(f"  操作系统: {os.name}")
    print(f"  CHROME_BIN: {os.environ.get('CHROME_BIN', '未设置')}")
    print(f"  CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH', '未设置')}")
    print(f"  MICRO_ENV: {os.environ.get('MICRO_ENV', '未设置')}")
    print(f"  Docker环境: {os.path.exists('/.dockerenv')}")
    print()
    
    try:
        # 测试基本连接
        test_basic_connectivity()
        
        # 测试代理连接
        test_proxy_connection()
        
        # 测试Selenium连接
        test_selenium_connection()
        
        # 测试论坛页面访问
        test_forum_page_access()
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试过程中发生错误: {str(e)}")
    
    print("\n测试完成")

if __name__ == "__main__":
    main()