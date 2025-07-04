#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import logging
import requests
import csv
import time
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

class Pan115Manager:
    """115网盘配置和操作管理器"""
    
    def __init__(self, config_file="config/pan115.json", config_manager=None):
        self.config_file = config_file
        self.cookie_file = "config/pan115_cookie.txt"  # Cookie单独存储文件
        self.config = self.load_config()
        self.config_manager = config_manager
        
        # 从ConfigManager获取user_agent，如果没有则使用默认值
        if config_manager:
            crawler_config = config_manager.load_config()
            self.ua = crawler_config.get('basic', {}).get('user_agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        else:
            self.ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        self.headers = {
            "User-Agent": self.ua,
            "Referer": "https://115.com/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        self._processed_magnets = set()  # 用于去重的磁力链接集合
        self.success_record_file = 'data/transfer_success_record.txt'  # 成功转存记录文件
        self._login_cache = {'valid': False, 'last_check': 0}  # 登录状态缓存
        self._cookies_cache = None  # Cookie缓存
        self._last_request_time = 0  # 上次请求时间
        self._folders_cache = {'data': None, 'last_update': 0}  # 文件夹列表缓存
    
    def load_config(self):
        """加载115网盘配置"""
        default_config = {
            "target_dir_id": "",
            "auto_transfer_enabled": False,
            "skip_duplicates": True,
            "skip_invalid_magnets": True,
            "magnet_column": "magnet_link",
            "deduplication_scope": "all",
            "request_interval": 5  # 115网盘请求间隔（秒）
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 合并默认配置
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
            else:
                # 创建默认配置文件
                os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                return default_config
        except Exception as e:
            logger.error(f"加载115网盘配置失败: {str(e)}")
            return default_config
    
    def save_config(self, config=None):
        """保存115网盘配置"""
        try:
            if config:
                self.config = config
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("115网盘配置保存成功")
            return True
        except Exception as e:
            logger.error(f"保存115网盘配置失败: {str(e)}")
            return False
    
    def _load_cookie(self):
        """从文件获取Cookie内容"""
        try:
            # 优先从cookie文件读取
            if os.path.exists(self.cookie_file):
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    cookie_content = f.read().strip()
                if cookie_content:
                    return cookie_content
            
            # 兼容旧配置：从JSON配置中读取
            cookie_content = self.config.get('cookie_content', '')
            if cookie_content:
                # 迁移到新的cookie文件
                self._save_cookie(cookie_content)
                # 从配置中移除cookie_content
                if 'cookie_content' in self.config:
                    del self.config['cookie_content']
                    self.save_config()
                return cookie_content.strip()
            
            raise ValueError("Cookie内容为空，请配置115网盘的Cookie")
        except Exception as e:
            logger.error(f"读取Cookie失败: {str(e)}")
            raise ValueError("Cookie读取失败，请检查配置")
    
    def _save_cookie(self, cookie_content):
        """保存Cookie到文件"""
        try:
            os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                f.write(cookie_content.strip())
            logger.info("Cookie保存成功")
            return True
        except Exception as e:
            logger.error(f"保存Cookie失败: {str(e)}")
            return False
    
    def _parse_cookie(self, cookie_str):
        """将Cookie字符串解析为字典"""
        cookies = {}
        for line in cookie_str.split(';'):
            if line.strip():
                parts = line.strip().split('=', 1)
                if len(parts) == 2:
                    key, value = parts
                    cookies[key] = value
        return cookies
    
    def _wait_for_rate_limit(self):
        """请求频率限制"""
        current_time = time.time()
        time_diff = current_time - self._last_request_time
        # 使用配置的请求间隔，最小500ms
        min_interval = max(self.config.get('request_interval', 5), 0.5)
        
        if time_diff < min_interval:
            sleep_time = min_interval - time_diff
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _validate_cookie_completeness(self, cookie_str):
        """验证Cookie的完整性，检查是否包含必要的参数"""
        required_params = ['UID', 'CID', 'SEID']
        missing_params = []
        
        for param in required_params:
            if param not in cookie_str:
                missing_params.append(param)
        
        if missing_params:
            logger.warning(f"Cookie缺少必要参数: {', '.join(missing_params)}")
            return False, missing_params
        
        # 检查参数值是否为空
        cookies = self._parse_cookie(cookie_str)
        empty_params = []
        for param in required_params:
            if not cookies.get(param):
                empty_params.append(param)
        
        if empty_params:
            logger.warning(f"Cookie参数值为空: {', '.join(empty_params)}")
            return False, empty_params
            
        return True, []
    
    def _handle_911_error(self):
        """处理911错误（账号验证），提供详细的诊断和解决建议"""
        logger.error("="*60)
        logger.error("检测到115网盘账号验证错误 (代码: 911)")
        logger.error("="*60)
        logger.error("可能的原因和解决方案:")
        logger.error("")
        logger.error("1. 账号安全验证触发:")
        logger.error("   - 115网盘检测到异常访问模式，要求人工验证")
        logger.error("   - 解决方案: 在浏览器中访问 https://115.com 完成人工验证")
        logger.error("")
        logger.error("2. Cookie过期或不完整:")
        logger.error("   - 当前Cookie可能已过期或缺少关键参数")
        logger.error("   - 解决方案: 重新登录115网盘，获取最新的完整Cookie")
        logger.error("")
        logger.error("3. 请求频率过高:")
        logger.error("   - 短时间内发送了过多请求")
        logger.error("   - 解决方案: 等待一段时间后再试，或减少批量操作的频率")
        logger.error("")
        logger.error("4. IP地址被限制:")
        logger.error("   - 当前IP可能被115网盘临时限制")
        logger.error("   - 解决方案: 更换网络环境或等待限制解除")
        logger.error("")
        logger.error("建议操作步骤:")
        logger.error("1. 在浏览器中访问 https://115.com 并完成任何验证")
        logger.error("2. 重新获取Cookie并更新配置")
        logger.error("3. 等待10-30分钟后重试")
        logger.error("4. 减少批量转存的数量，分批次处理")
        logger.error("="*60)
     
    def check_login(self, force_check=False):
        """检查115登录状态（带缓存优化）"""
        current_time = time.time()
        
        # 如果不是强制检查且缓存有效（5分钟内），直接返回缓存结果
        if not force_check and self._login_cache['valid'] and (current_time - self._login_cache['last_check']) < 300:
            return True
        
        try:
            self._wait_for_rate_limit()  # 请求频率限制
            
            cookie_str = self._load_cookie()
            cookies = self._parse_cookie(cookie_str)
            self._cookies_cache = cookies  # 缓存cookies
            
            url = "https://115.com/?ct=offline&ac=space"
            response = requests.get(url, headers=self.headers, cookies=cookies, timeout=15)
            response.raise_for_status()
            
            result = response.json()
            is_valid = result.get("state", False)
            
            # 更新缓存
            self._login_cache = {
                'valid': is_valid,
                'last_check': current_time
            }
            
            if is_valid:
                logger.info("115登录状态验证成功")
            else:
                logger.warning("115登录状态无效，请检查Cookie配置")
                
            return is_valid
        except Exception as e:
            logger.error(f"115登录检查失败: {str(e)}")
            self._login_cache['valid'] = False
            return False
    
    def get_folders(self, force_refresh=False):
        """获取115网盘文件夹列表（带缓存优化）"""
        current_time = time.time()
        cache_duration = 300  # 缓存5分钟
        
        # 如果不是强制刷新且缓存有效，直接返回缓存结果
        if not force_refresh and self._folders_cache['data'] is not None and \
           (current_time - self._folders_cache['last_update']) < cache_duration:
            logger.debug("使用缓存的文件夹列表")
            return self._folders_cache['data']
        
        try:
            self._wait_for_rate_limit()  # 请求频率限制
            
            cookie_str = self._load_cookie()
            cookies = self._parse_cookie(cookie_str)
            
            url = "https://aps.115.com/natsort/files.php?aid=1&cid=0&offset=0&limit=300&show_dir=1&natsort=1&format=json"
            response = requests.get(url, headers=self.headers, cookies=cookies, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data.get("state"):
                folders = [
                    {"id": item["cid"], "name": item["n"]} 
                    for item in data.get("data", []) 
                    if item.get("cid") and not item.get("fid")
                ]
                # 更新缓存
                self._folders_cache = {
                    'data': folders,
                    'last_update': current_time
                }
                logger.info(f"成功获取115文件夹列表，共{len(folders)}个文件夹")
                return folders
            else:
                logger.warning("115文件夹列表获取失败，返回状态为False")
                return []
        except Exception as e:
            logger.error(f"获取115文件夹列表失败: {str(e)}")
            # 如果有缓存数据，返回缓存（即使过期）
            if self._folders_cache['data'] is not None:
                logger.info("使用过期的缓存文件夹列表")
                return self._folders_cache['data']
            return []
    
    def submit_batch_magnets(self, magnet_links, progress_callback=None):
        """批量提交磁力链接到115离线下载（真正的批量提交）"""
        if not magnet_links:
            return {'success': True, 'total': 0, 'success_count': 0, 'failed_count': 0, 'message': '没有磁力链接需要处理'}
        
        logger.info(f"开始批量提交 {len(magnet_links)} 个磁力链接")
        
        # 首次尝试前验证Cookie完整性
        cookie_str = self._load_cookie()
        is_valid, missing_params = self._validate_cookie_completeness(cookie_str)
        if not is_valid:
            error_msg = f"Cookie配置不完整，缺少参数: {', '.join(missing_params)}。请重新获取完整的115网盘Cookie。"
            logger.error(error_msg)
            return {'success': False, 'message': error_msg}
        
        # 预先获取cookies，避免每次请求都解析
        cookies = self._parse_cookie(cookie_str)
        
        try:
            # 如果磁力链接数量超过100条，自动分批处理
            if len(magnet_links) > 100:
                logger.info(f"磁力链接数量 {len(magnet_links)} 超过100条，将分批处理")
                return self._submit_magnets_in_batches(magnet_links, cookies, progress_callback)
            
            # 尝试真正的批量提交（一次性提交所有磁力链接）
            success, result_data = self._submit_batch_magnets_api(magnet_links, cookies)
            
            if success:
                # 批量提交成功，记录所有成功的磁力链接
                for magnet_link in magnet_links:
                    self._processed_magnets.add(magnet_link)
                    self._save_success_record(magnet_link)
                
                if progress_callback:
                    progress_callback(100, f"批量提交完成: {len(magnet_links)} 个磁力链接")
                
                result = {
                    'success': True,
                    'total': len(magnet_links),
                    'success_count': len(magnet_links),
                    'failed_count': 0,
                    'message': f"批量提交成功: {len(magnet_links)} 个磁力链接"
                }
                logger.info(result['message'])
                return result
            else:
                # 批量提交失败，回退到逐个提交模式
                logger.warning("批量提交失败，回退到逐个提交模式")
                return self._submit_magnets_individually(magnet_links, cookies, progress_callback)
                
        except Exception as e:
            logger.error(f"批量提交异常: {str(e)}，回退到逐个提交模式")
            return self._submit_magnets_individually(magnet_links, cookies, progress_callback)
    
    def _submit_batch_magnets_api(self, magnet_links, cookies, retry_count=2):
        """尝试使用115网盘的批量提交API"""
        # 115网盘限制：一次最多提交100条磁力链接
        if len(magnet_links) > 100:
            logger.warning(f"磁力链接数量 {len(magnet_links)} 超过115网盘限制(100条)，将分批处理")
            return False, f"磁力链接数量超过115网盘限制(100条)，当前: {len(magnet_links)} 条"
        
        for attempt in range(retry_count + 1):
            try:
                self._wait_for_rate_limit()  # 请求频率限制
                
                url = "https://115.com/web/lixian/?ct=lixian&ac=add_task_urls"
                # 将多个磁力链接用换行符连接
                urls_data = "\n".join(magnet_links)
                data = {
                    "url[]": urls_data,
                    "wp_path_id": self.config.get('target_dir_id', '') or 0
                }
                
                response = requests.post(
                    url, 
                    headers=self.headers, 
                    cookies=cookies, 
                    data=data,
                    timeout=30  # 批量提交可能需要更长时间
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("state"):
                    logger.info(f"批量提交API成功: {len(magnet_links)} 个磁力链接")
                    return True, result
                else:
                    error_msg = result.get("error_msg", "未知错误")
                    error_code = result.get("errno", "")
                    
                    logger.warning(f"批量提交API失败: {error_msg} (代码: {error_code})")
                    
                    # 特殊处理911错误（账号验证）
                    if error_code == "911" or "验证账号" in error_msg:
                        self._handle_911_error()
                        return False, f"{error_msg} (代码: {error_code})"
                    
                    return False, f"{error_msg} (代码: {error_code})"
                    
            except requests.exceptions.Timeout:
                error_msg = f"批量提交请求超时 (尝试 {attempt + 1}/{retry_count + 1})"
                logger.warning(error_msg)
                if attempt < retry_count:
                    time.sleep(5)  # 超时后等待5秒重试
                    continue
                return False, error_msg
            except requests.exceptions.RequestException as e:
                error_msg = f"批量提交网络请求失败: {str(e)}"
                logger.error(error_msg)
                if attempt < retry_count:
                    time.sleep(3)
                    continue
                return False, error_msg
            except Exception as e:
                error_msg = f"批量提交未知错误: {str(e)}"
                logger.error(error_msg)
                return False, error_msg
        
        return False, "批量提交重试次数已用完"
    
    def _submit_magnets_in_batches(self, magnet_links, cookies, progress_callback=None, batch_size=100):
        """分批提交磁力链接（每批最多100条）"""
        logger.info(f"开始分批提交 {len(magnet_links)} 个磁力链接，每批 {batch_size} 条")
        
        total_success = 0
        total_failed = 0
        all_failed_details = []
        total_batches = (len(magnet_links) + batch_size - 1) // batch_size
        
        for batch_index in range(0, len(magnet_links), batch_size):
            batch_num = (batch_index // batch_size) + 1
            batch_links = magnet_links[batch_index:batch_index + batch_size]
            
            logger.info(f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_links)} 个磁力链接")
            
            try:
                # 尝试批量提交当前批次
                success, result_data = self._submit_batch_magnets_api(batch_links, cookies)
                
                if success:
                    # 批量提交成功
                    total_success += len(batch_links)
                    for magnet_link in batch_links:
                        self._processed_magnets.add(magnet_link)
                        self._save_success_record(magnet_link)
                    logger.info(f"第 {batch_num} 批批量提交成功: {len(batch_links)} 个磁力链接")
                else:
                    # 批量提交失败，回退到逐个提交
                    logger.warning(f"第 {batch_num} 批批量提交失败，回退到逐个提交模式")
                    individual_result = self._submit_magnets_individually(batch_links, cookies)
                    total_success += individual_result['success_count']
                    total_failed += individual_result['failed_count']
                    if individual_result.get('failed_details'):
                        all_failed_details.extend(individual_result['failed_details'])
                
                # 更新进度
                if progress_callback:
                    processed = min(batch_index + batch_size, len(magnet_links))
                    progress = int((processed / len(magnet_links)) * 100)
                    progress_callback(progress, f"已处理 {processed}/{len(magnet_links)} 个磁力链接 (第 {batch_num}/{total_batches} 批)")
                
                # 批次间延迟（除了最后一批）
                if batch_num < total_batches:
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"第 {batch_num} 批处理异常: {str(e)}，回退到逐个提交")
                individual_result = self._submit_magnets_individually(batch_links, cookies)
                total_success += individual_result['success_count']
                total_failed += individual_result['failed_count']
                if individual_result.get('failed_details'):
                    all_failed_details.extend(individual_result['failed_details'])
        
        result = {
            'success': True,
            'total': len(magnet_links),
            'success_count': total_success,
            'failed_count': total_failed,
            'message': f"分批提交完成: 成功 {total_success} 个, 失败 {total_failed} 个 (共 {total_batches} 批)"
        }
        
        if all_failed_details:
            result['failed_details'] = all_failed_details
        
        logger.info(result['message'])
        return result
    
    def _submit_magnets_individually(self, magnet_links, cookies, progress_callback=None):
        """逐个提交磁力链接（回退模式）"""
        logger.info(f"使用逐个提交模式处理 {len(magnet_links)} 个磁力链接")
        
        success_count = 0
        failed_count = 0
        failed_details = []
        
        for i, magnet_link in enumerate(magnet_links):
            try:
                success, message = self._submit_single_magnet(magnet_link, cookies)
                if success:
                    success_count += 1
                    self._processed_magnets.add(magnet_link)
                    self._save_success_record(magnet_link)
                else:
                    failed_count += 1
                    failed_details.append({
                        'magnet': self._get_magnet_name(magnet_link),
                        'error': message
                    })
                
                # 进度回调
                if progress_callback:
                    progress = int(((i + 1) / len(magnet_links)) * 100)
                    progress_callback(progress, f"已处理 {i + 1}/{len(magnet_links)} 个磁力链接")
                
                # 请求频率限制
                self._wait_for_rate_limit()
                
            except Exception as e:
                failed_count += 1
                failed_details.append({
                    'magnet': self._get_magnet_name(magnet_link),
                    'error': str(e)
                })
        
        result = {
            'success': True,
            'total': len(magnet_links),
            'success_count': success_count,
            'failed_count': failed_count,
            'message': f"逐个提交完成: 成功 {success_count} 个, 失败 {failed_count} 个"
        }
        
        if failed_details:
            result['failed_details'] = failed_details
        
        logger.info(result['message'])
        return result
    
    def _submit_single_magnet(self, magnet_link, cookies, retry_count=2):
        """提交单个磁力链接（内部方法，复用cookies）"""
        for attempt in range(retry_count + 1):
            try:
                url = "https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
                data = {
                    "url": magnet_link,
                    "wp_path_id": self.config.get('target_dir_id', '') or 0
                }
                
                response = requests.post(
                    url, 
                    headers=self.headers, 
                    cookies=cookies, 
                    data=data
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("state"):
                    logger.debug(f"磁力链接提交成功: {self._get_magnet_name(magnet_link)}")
                    return True, "提交成功"
                else:
                    error_msg = result.get("error_msg", "未知错误")
                    error_code = result.get("errno", "")
                    
                    # 详细错误日志
                    logger.warning(f"磁力链接提交失败: {self._get_magnet_name(magnet_link)}, 错误: {error_msg} (代码: {error_code})")
                    
                    # 特殊处理911错误（账号验证）
                    if error_code == "911" or "验证账号" in error_msg:
                        self._handle_911_error()
                        return False, f"{error_msg} (代码: {error_code}) - 需要账号验证，请查看日志获取解决方案"
                    
                    # 如果是登录相关错误，不重试（因为cookies是共享的）
                    if "登录" in error_msg or "cookie" in error_msg.lower() or error_code in ["40001", "40002"]:
                        return False, f"{error_msg} (代码: {error_code})"
                    
                    return False, f"{error_msg} (代码: {error_code})"
                    
            except requests.exceptions.Timeout:
                error_msg = f"请求超时 (尝试 {attempt + 1}/{retry_count + 1})"
                logger.warning(f"磁力链接提交超时: {self._get_magnet_name(magnet_link)}, {error_msg}")
                if attempt < retry_count:
                    time.sleep(3)  # 超时后等待3秒重试
                    continue
                return False, error_msg
            except requests.exceptions.RequestException as e:
                error_msg = f"网络请求失败: {str(e)}"
                logger.error(f"磁力链接提交网络错误: {self._get_magnet_name(magnet_link)}, {error_msg}")
                if attempt < retry_count:
                    time.sleep(2)
                    continue
                return False, error_msg
            except Exception as e:
                error_msg = f"未知错误: {str(e)}"
                logger.error(f"磁力链接提交异常: {self._get_magnet_name(magnet_link)}, {error_msg}")
                return False, error_msg
        
        return False, "重试次数已用完"
    
    def submit_magnet(self, magnet_link, retry_count=2):
        """提交磁力链接到115离线下载（带重试机制）"""
        # 首次尝试前验证Cookie完整性
        cookie_str = self._load_cookie()
        is_valid, missing_params = self._validate_cookie_completeness(cookie_str)
        if not is_valid:
            error_msg = f"Cookie配置不完整，缺少参数: {', '.join(missing_params)}。请重新获取完整的115网盘Cookie。"
            logger.error(error_msg)
            return False, error_msg
        
        for attempt in range(retry_count + 1):
            try:
                self._wait_for_rate_limit()  # 请求频率限制
                
                # 直接获取cookies，避免缓存问题
                cookie_str = self._load_cookie()
                cookies = self._parse_cookie(cookie_str)
                
                url = "https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
                data = {
                    "url": magnet_link,
                    "wp_path_id": self.config.get('target_dir_id', '') or 0
                }
                
                response = requests.post(
                    url, 
                    headers=self.headers, 
                    cookies=cookies, 
                    data=data
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("state"):
                    logger.debug(f"磁力链接提交成功: {self._get_magnet_name(magnet_link)}")
                    return True, "提交成功"
                else:
                    error_msg = result.get("error_msg", "未知错误")
                    error_code = result.get("errno", "")
                    
                    # 详细错误日志
                    logger.warning(f"磁力链接提交失败: {self._get_magnet_name(magnet_link)}, 错误: {error_msg} (代码: {error_code})")
                    
                    # 特殊处理911错误（账号验证）
                    if error_code == "911" or "验证账号" in error_msg:
                        self._handle_911_error()
                        return False, f"{error_msg} (代码: {error_code}) - 需要账号验证，请查看日志获取解决方案"
                    
                    # 如果是登录相关错误，清除缓存
                    if "登录" in error_msg or "cookie" in error_msg.lower() or error_code in ["40001", "40002"]:
                        self._login_cache['valid'] = False
                        self._cookies_cache = None
                        if attempt < retry_count:
                            logger.info(f"登录状态异常，重试第 {attempt + 1} 次")
                            time.sleep(2)  # 等待2秒后重试
                            continue
                    
                    return False, f"{error_msg} (代码: {error_code})"
                    
            except requests.exceptions.Timeout:
                error_msg = f"请求超时 (尝试 {attempt + 1}/{retry_count + 1})"
                logger.warning(f"磁力链接提交超时: {self._get_magnet_name(magnet_link)}, {error_msg}")
                if attempt < retry_count:
                    time.sleep(3)  # 超时后等待3秒重试
                    continue
                return False, error_msg
            except requests.exceptions.RequestException as e:
                error_msg = f"网络请求失败: {str(e)}"
                logger.error(f"磁力链接提交网络错误: {self._get_magnet_name(magnet_link)}, {error_msg}")
                if attempt < retry_count:
                    time.sleep(2)
                    continue
                return False, error_msg
            except Exception as e:
                error_msg = f"未知错误: {str(e)}"
                logger.error(f"磁力链接提交异常: {self._get_magnet_name(magnet_link)}, {error_msg}")
                return False, error_msg
        
        return False, "重试次数已用完"
    
    def _get_magnet_name(self, magnet_link):
        """从磁力链接中提取文件名(dn参数)"""
        try:
            query = parse_qs(urlparse(magnet_link).query)
            return query.get("dn", ["磁力链接"])[0][:50] + "..."
        except:
            return magnet_link[:30] + "..."
    
    def _is_valid_magnet(self, magnet_link):
        """检查磁力链接是否有效"""
        if not magnet_link or not isinstance(magnet_link, str):
            return False
        
        magnet_link = magnet_link.strip()
        if not magnet_link.startswith("magnet:?"):
            return False
        
        # 检查是否包含乱码（简单检测）
        try:
            magnet_link.encode('utf-8')
            # 检查是否包含基本的磁力链接参数
            if 'xt=' not in magnet_link:
                return False
            return True
        except UnicodeEncodeError:
            return False
    
    def _load_processed_magnets(self, current_csv_file=None):
        """加载已成功转存的磁力链接（用于去重）"""
        deduplication_scope = self.config.get('deduplication_scope', 'all')
        
        try:
            # 确保data目录存在
            data_dir = 'data'
            if not os.path.exists(data_dir):
                os.makedirs(data_dir)
            
            if deduplication_scope == 'current' and current_csv_file:
                # 仅对当前文件去重（检查文件内部重复）
                magnet_column = self.config.get('magnet_column', 'magnet_link')
                try:
                    with open(current_csv_file, 'r', encoding='utf-8-sig') as f:
                        reader = csv.DictReader(f)
                        if magnet_column in reader.fieldnames:
                            seen_magnets = set()
                            for row in reader:
                                magnet = row.get(magnet_column, '').strip()
                                if self._is_valid_magnet(magnet):
                                    if magnet in seen_magnets:
                                        self._processed_magnets.add(magnet)  # 标记为重复
                                    else:
                                        seen_magnets.add(magnet)
                except Exception as e:
                    logger.warning(f"读取当前CSV文件失败 {current_csv_file}: {str(e)}")
            elif deduplication_scope == 'all':
                # 从成功转存记录文件加载已转存的磁力链接
                if os.path.exists(self.success_record_file):
                    try:
                        with open(self.success_record_file, 'r', encoding='utf-8') as f:
                            for line in f:
                                magnet = line.strip()
                                if magnet and self._is_valid_magnet(magnet):
                                    self._processed_magnets.add(magnet)
                        logger.info(f"已加载 {len(self._processed_magnets)} 个成功转存的磁力链接用于去重")
                    except Exception as e:
                        logger.warning(f"读取成功转存记录失败: {str(e)}")
                else:
                    logger.info("成功转存记录文件不存在，将创建新的记录文件")
            
        except Exception as e:
            logger.error(f"加载成功转存记录失败: {str(e)}")
    
    def process_csv_file(self, csv_file, progress_callback=None, force_transfer=False):
        """处理CSV文件中的磁力链接（使用批量提交优化）"""
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"CSV文件不存在: {csv_file}")
        
        # 检查配置（手动转存时跳过自动转存开关检查）
        if not force_transfer and not self.config.get('auto_transfer_enabled', False):
            logger.info("115网盘自动转存未启用")
            return {'success': False, 'message': '115网盘自动转存未启用'}
        
        if not self.check_login():
            raise ValueError("115登录状态无效，请检查Cookie配置")
        
        # 加载历史磁力链接用于去重
        if self.config.get('skip_duplicates', True):
            self._load_processed_magnets(csv_file)
        
        magnet_column = self.config.get('magnet_column', 'magnet_link')
        
        # 读取CSV文件
        magnets = []
        total_read = 0
        invalid_count = 0
        duplicate_count = 0
        
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if magnet_column not in reader.fieldnames:
                raise ValueError(f"CSV中找不到列: {magnet_column}")
            
            for row in reader:
                magnet = row.get(magnet_column, '').strip()
                total_read += 1
                
                # 跳过空磁力链接
                if not magnet:
                    continue
                
                # 验证磁力链接
                if not self._is_valid_magnet(magnet):
                    invalid_count += 1
                    logger.debug(f"跳过无效磁力链接: {magnet[:50]}...")
                    if self.config.get('skip_invalid_magnets', True):
                        continue
                    else:
                        magnets.append(magnet)
                        continue
                
                # 去重检查
                if self.config.get('skip_duplicates', True):
                    if magnet in self._processed_magnets:
                        duplicate_count += 1
                        logger.debug(f"跳过重复磁力链接: {magnet[:50]}...")
                        continue
                
                magnets.append(magnet)
        
        logger.info(f"CSV文件分析: 总计{total_read}行, 无效{invalid_count}个, 重复{duplicate_count}个, 待处理{len(magnets)}个")
        
        if not magnets:
            logger.info("没有找到需要处理的磁力链接")
            return {'success': True, 'message': '没有找到需要处理的磁力链接', 'processed': 0, 'skipped': 0}
        
        logger.info(f"准备批量处理 {len(magnets)} 个磁力链接")
        
        # 使用批量提交方法
        result = self.submit_batch_magnets(magnets, progress_callback)
        
        # 添加统计信息
        result['total_read'] = total_read
        result['invalid_count'] = invalid_count
        result['duplicate_count'] = duplicate_count
        
        # 更新消息
        if invalid_count > 0 or duplicate_count > 0:
            result['message'] += f"（跳过: 无效{invalid_count}个, 重复{duplicate_count}个）"
        
        logger.info(result['message'])
        return result
    
    def get_config(self):
        """获取当前配置（包含cookie内容）"""
        config = self.config.copy()
        # 添加cookie内容到配置中返回给前端
        try:
            config['cookie_content'] = self._load_cookie()
        except:
            config['cookie_content'] = ''
        return config
    
    def update_config(self, new_config):
        """更新配置（包含cookie处理）"""
        # 处理cookie更新
        if 'cookie_content' in new_config:
            cookie_content = new_config.pop('cookie_content')
            if cookie_content:
                self._save_cookie(cookie_content)
        
        # 更新其他配置
        self.config.update(new_config)
        return self.save_config()
    
    def _save_success_record(self, magnet):
        """保存成功转存的磁力链接到记录文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.success_record_file), exist_ok=True)
            
            # 追加写入成功转存的磁力链接
            with open(self.success_record_file, 'a', encoding='utf-8') as f:
                f.write(magnet + '\n')
        except Exception as e:
            logger.error(f"保存成功转存记录失败: {str(e)}")
    
    def extract_magnets_to_cache(self, csv_file):
        """从CSV文件提取磁力链接并去重，保存到缓存txt文件"""
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"CSV文件不存在: {csv_file}")
        
        # 生成缓存文件路径
        csv_basename = os.path.splitext(os.path.basename(csv_file))[0]
        cache_file = os.path.join('data', f'{csv_basename}_magnets_cache.txt')
        
        # 确保data目录存在
        os.makedirs('data', exist_ok=True)
        
        # 加载历史磁力链接用于去重
        if self.config.get('skip_duplicates', True):
            self._load_processed_magnets(csv_file)
        
        magnet_column = self.config.get('magnet_column', 'magnet_link')
        
        # 读取CSV文件并去重
        unique_magnets = set()
        total_read = 0
        invalid_count = 0
        duplicate_count = 0
        
        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            if magnet_column not in reader.fieldnames:
                raise ValueError(f"CSV中找不到列: {magnet_column}")
            
            for row in reader:
                magnet = row.get(magnet_column, '').strip()
                total_read += 1
                
                # 跳过空磁力链接
                if not magnet:
                    continue
                
                # 验证磁力链接
                if not self._is_valid_magnet(magnet):
                    invalid_count += 1
                    logger.debug(f"跳过无效磁力链接: {magnet[:50]}...")
                    if self.config.get('skip_invalid_magnets', True):
                        continue
                
                # 去重检查
                if self.config.get('skip_duplicates', True):
                    if magnet in self._processed_magnets or magnet in unique_magnets:
                        duplicate_count += 1
                        logger.debug(f"跳过重复磁力链接: {magnet[:50]}...")
                        continue
                
                unique_magnets.add(magnet)
        
        # 保存去重后的磁力链接到缓存文件
        with open(cache_file, 'w', encoding='utf-8') as f:
            for magnet in unique_magnets:
                f.write(magnet + '\n')
        
        logger.info(f"磁力链接缓存完成: 总计{total_read}行, 无效{invalid_count}个, 重复{duplicate_count}个, 缓存{len(unique_magnets)}个")
        logger.info(f"缓存文件保存至: {cache_file}")
        
        return {
            'cache_file': cache_file,
            'total_read': total_read,
            'invalid_count': invalid_count,
            'duplicate_count': duplicate_count,
            'cached_count': len(unique_magnets)
        }
    
    def process_cache_file(self, cache_file, batch_size=100, progress_callback=None):
        """从缓存txt文件分批处理磁力链接"""
        if not os.path.exists(cache_file):
            raise FileNotFoundError(f"缓存文件不存在: {cache_file}")
        
        if not self.check_login():
            raise ValueError("115登录状态无效，请检查Cookie配置")
        
        # 读取缓存文件中的所有磁力链接
        magnets = []
        with open(cache_file, 'r', encoding='utf-8') as f:
            for line in f:
                magnet = line.strip()
                if magnet and self._is_valid_magnet(magnet):
                    magnets.append(magnet)
        
        if not magnets:
            logger.info("缓存文件中没有找到有效的磁力链接")
            return {'success': True, 'message': '缓存文件中没有找到有效的磁力链接', 'total_batches': 0}
        
        # 分批处理
        total_batches = (len(magnets) + batch_size - 1) // batch_size
        logger.info(f"准备分{total_batches}批处理 {len(magnets)} 个磁力链接，每批最多{batch_size}个")
        
        total_success = 0
        total_failed = 0
        all_failed_details = []
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(magnets))
            batch_magnets = magnets[start_idx:end_idx]
            
            logger.info(f"处理第 {batch_num + 1}/{total_batches} 批，包含 {len(batch_magnets)} 个磁力链接")
            
            # 处理当前批次
            batch_result = self.submit_batch_magnets(batch_magnets, None)
            
            total_success += batch_result.get('success_count', 0)
            total_failed += batch_result.get('failed_count', 0)
            
            if batch_result.get('failed_details'):
                all_failed_details.extend(batch_result['failed_details'])
            
            # 进度回调
            if progress_callback:
                progress = int(((batch_num + 1) / total_batches) * 100)
                progress_callback(progress, f"已完成 {batch_num + 1}/{total_batches} 批次")
            
            # 批次间等待，避免请求过于频繁
            if batch_num < total_batches - 1:  # 不是最后一批
                time.sleep(2)
        
        result = {
            'success': True,
            'total_batches': total_batches,
            'total_magnets': len(magnets),
            'success_count': total_success,
            'failed_count': total_failed,
            'message': f"分批处理完成: {total_batches}批次, 成功 {total_success} 个, 失败 {total_failed} 个"
        }
        
        if all_failed_details:
            result['failed_details'] = all_failed_details
        
        logger.info(result['message'])
        return result
    
    def process_csv_with_cache(self, csv_file, batch_size=100, progress_callback=None, force_transfer=False):
        """使用缓存机制处理CSV文件：先提取到缓存，再分批处理"""
        # 检查配置（手动转存时跳过自动转存开关检查）
        if not force_transfer and not self.config.get('auto_transfer_enabled', False):
            logger.info("115网盘自动转存未启用")
            return {'success': False, 'message': '115网盘自动转存未启用'}
        
        try:
            # 第一步：提取磁力链接到缓存
            logger.info("第一步：从CSV文件提取磁力链接到缓存")
            cache_result = self.extract_magnets_to_cache(csv_file)
            
            if cache_result['cached_count'] == 0:
                return {
                    'success': True,
                    'message': '没有找到需要处理的磁力链接',
                    'cache_result': cache_result
                }
            
            # 第二步：从缓存分批处理
            logger.info("第二步：从缓存文件分批处理磁力链接")
            process_result = self.process_cache_file(cache_result['cache_file'], batch_size, progress_callback)
            
            # 合并结果
            final_result = {
                'success': True,
                'cache_result': cache_result,
                'process_result': process_result,
                'message': f"处理完成: 缓存{cache_result['cached_count']}个, 成功{process_result['success_count']}个, 失败{process_result['failed_count']}个"
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"CSV缓存处理失败: {str(e)}")
            return {'success': False, 'message': f'处理失败: {str(e)}'}