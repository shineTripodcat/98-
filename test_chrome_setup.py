#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Chrome和ChromeDriver设置
用于验证Docker环境中的配置是否正确
"""

import os
import sys
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from config_manager import ConfigManager

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_chrome_setup():
    """测试Chrome设置"""
    logger.info("开始测试Chrome设置...")
    
    # 环境信息
    logger.info(f"Python版本: {sys.version}")
    logger.info(f"操作系统: {os.name}")
    logger.info(f"当前工作目录: {os.getcwd()}")
    
    # 环境变量检查
    logger.info("=== 环境变量检查 ===")
    logger.info(f"CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH')}")
    logger.info(f"CHROME_BIN: {os.environ.get('CHROME_BIN')}")
    logger.info(f"ALPINE_ENV: {os.environ.get('ALPINE_ENV')}")
    logger.info(f"MICRO_ENV: {os.environ.get('MICRO_ENV')}")
    logger.info(f"Docker环境检查: {os.path.exists('/.dockerenv')}")
    
    # 文件路径检查
    logger.info("=== 文件路径检查 ===")
    paths_to_check = [
        '/usr/bin/chromedriver',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
        '/.dockerenv'
    ]
    
    for path in paths_to_check:
        exists = os.path.exists(path)
        logger.info(f"{path}: {'存在' if exists else '不存在'}")
    
    # 加载配置
    logger.info("=== 配置加载测试 ===")
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config()
        logger.info(f"配置文件: {config_manager.config_file}")
        logger.info(f"Chrome路径配置: {config.get('chrome_path')}")
        logger.info(f"Chrome选项数量: {len(config.get('chrome_options', []))}")
        logger.info(f"Headless模式: {config.get('headless')}")
    except Exception as e:
        logger.error(f"配置加载失败: {e}")
        return False
    
    # Chrome驱动测试
    logger.info("=== Chrome驱动测试 ===")
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        # 设置Chrome路径
        chrome_path = config.get('chrome_path')
        if chrome_path and os.path.exists(chrome_path):
            options.binary_location = chrome_path
            logger.info(f"使用Chrome路径: {chrome_path}")
        elif os.environ.get('CHROME_BIN'):
            chrome_bin = os.environ.get('CHROME_BIN')
            if os.path.exists(chrome_bin):
                options.binary_location = chrome_bin
                logger.info(f"使用环境变量Chrome路径: {chrome_bin}")
        
        # 设置ChromeDriver路径
        chromedriver_path = None
        if os.environ.get('CHROMEDRIVER_PATH'):
            chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
        elif os.environ.get('ALPINE_ENV') or os.path.exists('/.dockerenv'):
            chromedriver_path = '/usr/bin/chromedriver'
        elif os.path.exists('/usr/bin/chromedriver'):
            chromedriver_path = '/usr/bin/chromedriver'
        
        if not chromedriver_path or not os.path.exists(chromedriver_path):
            logger.error(f"ChromeDriver路径无效: {chromedriver_path}")
            return False
        
        logger.info(f"使用ChromeDriver路径: {chromedriver_path}")
        
        # 创建驱动
        service = webdriver.chrome.service.Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        # 简单测试
        driver.get('data:text/html,<html><body><h1>Test Page</h1></body></html>')
        title = driver.title
        logger.info(f"页面标题: {title}")
        
        driver.quit()
        logger.info("Chrome驱动测试成功！")
        return True
        
    except Exception as e:
        logger.error(f"Chrome驱动测试失败: {e}")
        return False

if __name__ == '__main__':
    success = test_chrome_setup()
    if success:
        logger.info("✅ 所有测试通过！")
        sys.exit(0)
    else:
        logger.error("❌ 测试失败！")
        sys.exit(1)