#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigManager:
    """配置管理器"""
    
    # 预定义的用户代理选项
    USER_AGENT_OPTIONS = {
        'chrome_windows': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'chrome_linux': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    def __init__(self, config_file=None):
        if config_file is None:
            # 统一只用基础配置文件
            config_file = 'config/crawler_config.json'
        self.config_file = config_file
        self.default_config = {
            # 基本配置
            'headless': True,
            'user_agent': self.USER_AGENT_OPTIONS['chrome_windows'],
            'proxy': '',  # 代理设置（可选），格式: http://127.0.0.1:7890
            'random_delay': 5,
            'min_wait_time': 2,
            'debug': False,
            
            # 网站配置
            'base_url': 'https://s9ko.avp76.net',
            
            # 论坛配置
            'forums': [
                {
                    'name': '默认论坛',
                    'fid': '36',
                    'typeid': '672',
                    'tid_file': 'tids36.txt',
                    'start_page': 1,
                    'end_page': 430,
                    'enabled': True
                }
            ],
            
            # 爬取配置
            'mode': 'update_magnets',
            'recent_tids': 30,
            'last_crawl_page': 0,
            'max_pages_per_run': 5,
            'worker_count': 5,
            'max_tid': '0',
            
            # 文件配置
            'data_dir': './data',
            'result_csv': 'results.csv',
            'tid_file': 'tids.txt',
            
            # 浏览器配置
            'chrome_path': '',
            'chrome_options': [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-extensions',
                '--disable-popup-blocking',
                '--disable-web-security',
                '--disable-infobars',
                '--ignore-certificate-errors',
                '--hide-scrollbars',
                '--mute-audio'
            ],
            
            # 调度配置
            'schedule': {
                'enabled': False,
                'cron_expression': '0 */6 * * *',  # 每6小时执行一次
                'mode': 'update_magnets'
            },
            
            # 通知配置
            'notifications': {
                'enabled': False,
                'webhook_url': '',
                'email': {
                    'enabled': False,
                    'smtp_server': '',
                    'smtp_port': 587,
                    'username': '',
                    'password': '',
                    'to_email': ''
                }
            }
        }
        
        # 确保配置目录存在
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 合并默认配置（确保新增的配置项存在）
                merged_config = self._merge_config(self.default_config, config)
                
                # 确保max_tid字段存在
                if 'max_tid' not in merged_config:
                    merged_config['max_tid'] = '0'
                
                return merged_config
            else:
                logger.info(f"配置文件不存在，使用默认配置: {self.config_file}")
                default_with_max_tid = self.default_config.copy()
                default_with_max_tid['max_tid'] = '0'
                self.save_config(default_with_max_tid)
                return default_with_max_tid
        
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")
            default_with_max_tid = self.default_config.copy()
            default_with_max_tid['max_tid'] = '0'
            return default_with_max_tid
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """保存配置"""
        try:
            # 验证配置
            validated_config = self._validate_config(config)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(validated_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已保存: {self.config_file}")
            return True
        
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            return False
    
    def _merge_config(self, default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """合并配置（递归合并）"""
        result = default.copy()
        
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """验证配置"""
        validated = config.copy()
        
        # 验证基本类型
        if not isinstance(validated.get('headless'), bool):
            validated['headless'] = True
        
        if not isinstance(validated.get('debug'), bool):
            validated['debug'] = False
        
        if not isinstance(validated.get('random_delay'), int) or validated['random_delay'] < 0:
            validated['random_delay'] = 5
        
        if not isinstance(validated.get('min_wait_time'), int) or validated['min_wait_time'] < 0:
            validated['min_wait_time'] = 2
        
        if not isinstance(validated.get('worker_count'), int) or validated['worker_count'] < 1:
            validated['worker_count'] = 5
        
        if not isinstance(validated.get('max_pages_per_run'), int) or validated['max_pages_per_run'] < 1:
            validated['max_pages_per_run'] = 5
        
        # 验证URL
        if not validated.get('base_url') or not validated['base_url'].startswith('http'):
            validated['base_url'] = self.default_config['base_url']
        
        # 验证代理设置
        proxy = validated.get('proxy', '')
        if proxy and not (proxy.startswith('http://') or proxy.startswith('https://') or proxy.startswith('socks5://')):
            logger.warning(f"代理格式不正确: {proxy}，已清空代理设置")
            validated['proxy'] = ''
        
        # 验证模式
        valid_modes = ['crawl_tids', 'crawl_magnets', 'update_magnets']
        if validated.get('mode') not in valid_modes:
            validated['mode'] = 'update_magnets'
        
        # 验证论坛配置
        if not isinstance(validated.get('forums'), list):
            validated['forums'] = self.default_config['forums']
        
        # 验证每个论坛配置
        for forum in validated['forums']:
            if not isinstance(forum, dict):
                continue
            
            if not forum.get('fid'):
                forum['fid'] = '36'
            
            if not forum.get('typeid'):
                forum['typeid'] = '672'
            
            if not isinstance(forum.get('start_page'), int) or forum['start_page'] < 1:
                forum['start_page'] = 1
            
            if not isinstance(forum.get('end_page'), int) or forum['end_page'] < forum['start_page']:
                forum['end_page'] = 100
            
            if not isinstance(forum.get('enabled'), bool):
                forum['enabled'] = True
        
        # 确保数据目录存在
        data_dir = validated.get('data_dir', './data')
        os.makedirs(data_dir, exist_ok=True)
        
        return validated
    
    def get_data_dir(self) -> str:
        """获取数据目录"""
        config = self.load_config()
        data_dir = config.get('data_dir', './data')
        os.makedirs(data_dir, exist_ok=True)
        return data_dir
    
    def update_max_tid(self, max_tid: str) -> bool:
        """更新最大TID"""
        try:
            config = self.load_config()
            config['max_tid'] = max_tid
            return self.save_config(config)
        except Exception as e:
            logger.error(f"更新最大TID失败: {str(e)}")
            return False
    
    def update_last_crawl_page(self, page: int) -> bool:
        """更新最后爬取页码"""
        try:
            config = self.load_config()
            config['last_crawl_page'] = page
            return self.save_config(config)
        except Exception as e:
            logger.error(f"更新最后爬取页码失败: {str(e)}")
            return False
    
    def get_forum_configs(self) -> list:
        """获取启用的论坛配置"""
        config = self.load_config()
        forums = config.get('forums', [])
        return [forum for forum in forums if forum.get('enabled', True)]
    
    def export_config(self, filepath: str) -> bool:
        """导出配置"""
        try:
            config = self.load_config()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"导出配置失败: {str(e)}")
            return False
    
    def import_config(self, filepath: str) -> bool:
        """导入配置"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return self.save_config(config)
        except Exception as e:
            logger.error(f"导入配置失败: {str(e)}")
            return False
    
    def get_user_agent_options(self) -> Dict[str, str]:
        """获取用户代理选项"""
        return self.USER_AGENT_OPTIONS.copy()
    
    def get_user_agent_display_names(self) -> Dict[str, str]:
        """获取用户代理显示名称"""
        return {
            'chrome_windows': 'Chrome (Windows 64位)',
            'chrome_linux': 'Chrome (Linux)'
        }