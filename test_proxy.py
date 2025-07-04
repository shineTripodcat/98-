#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
代理配置测试脚本
用于验证代理设置是否正常工作
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_requests_proxy():
    """测试requests库的代理设置"""
    logger.info("测试requests库代理设置...")
    
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config()
        proxy = config.get('proxy', '')
        
        if not proxy:
            logger.warning("未配置代理，跳过requests代理测试")
            return False
        
        proxies = {
            'http': proxy,
            'https': proxy
        }
        
        logger.info(f"使用代理: {proxy}")
        
        # 测试HTTP请求
        response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
        logger.info(f"HTTP请求成功，IP: {response.json()}")
        
        # 测试HTTPS请求
        response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=10)
        logger.info(f"HTTPS请求成功，IP: {response.json()}")
        
        return True
        
    except Exception as e:
        logger.error(f"requests代理测试失败: {str(e)}")
        return False

def test_selenium_proxy():
    """测试Selenium的代理设置"""
    logger.info("测试Selenium代理设置...")
    
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config()
        proxy = config.get('proxy', '')
        
        if not proxy:
            logger.warning("未配置代理，跳过Selenium代理测试")
            return False
        
        # 创建Chrome选项
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument(f'--proxy-server={proxy}')
        
        logger.info(f"使用代理: {proxy}")
        
        # 创建WebDriver
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            # 访问IP检测网站
            driver.get('http://httpbin.org/ip')
            page_source = driver.page_source
            logger.info(f"Selenium代理测试成功，页面内容: {page_source[:200]}...")
            return True
            
        finally:
            driver.quit()
        
    except Exception as e:
        logger.error(f"Selenium代理测试失败: {str(e)}")
        return False

def main():
    """主函数"""
    logger.info("开始代理配置测试")
    
    # 测试requests代理
    requests_ok = test_requests_proxy()
    
    # 测试Selenium代理
    selenium_ok = test_selenium_proxy()
    
    # 输出测试结果
    logger.info("\n=== 代理测试结果 ===")
    logger.info(f"requests代理: {'✓ 成功' if requests_ok else '✗ 失败'}")
    logger.info(f"Selenium代理: {'✓ 成功' if selenium_ok else '✗ 失败'}")
    
    if requests_ok and selenium_ok:
        logger.info("所有代理测试通过！")
        return 0
    else:
        logger.warning("部分或全部代理测试失败")
        return 1

if __name__ == '__main__':
    sys.exit(main())