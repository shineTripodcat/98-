#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 python-115 库的115网盘管理器
支持扫码登录、手动输入cookie、批量磁力链接推送、定时文件移动等功能
"""

import json
import os
import logging
import time
import threading
import schedule
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Callable, Union
from pathlib import Path

# 需要安装: pip install python-115
try:
    from p115 import P115Client
    from p115.component.client import P115Client as P115ClientComponent
except ImportError:
    raise ImportError("请安装 python-115 库: pip install python-115")

logger = logging.getLogger(__name__)

class Pan115Manager:
    """基于 python-115 库的115网盘管理器"""
    
    def __init__(self, config_file="config/pan115.json", config_manager=None):
        self.config_file = config_file
        self.cookie_file = "config/pan115_cookie.txt"
        self.config = self.load_config()
        self.config_manager = config_manager
        
        # 115客户端实例
        self._client: Optional[P115Client] = None
        self._client_lock = threading.Lock()
        
        # 缓存和状态
        self._login_cache = {'valid': False, 'last_check': 0}
        self._processed_magnets = set()
        self.success_record_file = 'data/transfer_success_record.txt'
        
        # 定时任务相关
        self._scheduler_thread = None
        self._scheduler_running = False
        
        # 初始化数据目录
        os.makedirs('data', exist_ok=True)
        os.makedirs('config', exist_ok=True)
    
    def load_config(self) -> Dict:
        """加载配置"""
        default_config = {
            "target_dir_id": "",
            "auto_transfer_enabled": False,
            "skip_duplicates": True,
            "skip_invalid_magnets": True,
            "magnet_column": "magnet_link",
            "deduplication_scope": "all",
            "request_interval": 2,
            "batch_size": 50,
            "auto_move_enabled": False,
            "auto_move_source_dir_id": "",
            "auto_move_target_dir_id": "",
            "auto_move_interval_hours": 24,
            "auto_move_cron": "0 2 * * *",
            "qr_login_enabled": True,
            "cookie_auto_refresh": True
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
            logger.error(f"加载配置失败: {str(e)}")
            return default_config
    
    def save_config(self, config: Optional[Dict] = None) -> bool:
        """保存配置"""
        try:
            if config:
                self.config = config
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info("配置保存成功")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
            return False
    
    def get_config(self) -> Dict:
        """获取当前配置（包含cookie内容）"""
        config = self.config.copy()
        # 添加cookie内容到配置中返回给前端
        try:
            config['cookie_content'] = self._load_cookie()
        except:
            config['cookie_content'] = ''
        return config
    
    def update_config(self, new_config: Dict) -> bool:
        """更新配置（包含cookie处理）"""
        # 处理cookie更新
        if 'cookie_content' in new_config:
            cookie_content = new_config.pop('cookie_content')
            if cookie_content:
                self._save_cookie(cookie_content)
        
        # 更新其他配置
        self.config.update(new_config)
        return self.save_config()
    
    def _load_cookie(self) -> str:
        """从文件获取Cookie内容"""
        try:
            if os.path.exists(self.cookie_file):
                with open(self.cookie_file, 'r', encoding='utf-8') as f:
                    cookie_content = f.read().strip()
                if cookie_content:
                    return cookie_content
            
            # 兼容旧配置
            cookie_content = self.config.get('cookie_content', '')
            if cookie_content:
                self._save_cookie(cookie_content)
                if 'cookie_content' in self.config:
                    del self.config['cookie_content']
                    self.save_config()
                return cookie_content.strip()
            
            raise ValueError("Cookie内容为空，请配置115网盘的Cookie")
        except Exception as e:
            logger.error(f"读取Cookie失败: {str(e)}")
            raise ValueError("Cookie读取失败，请检查配置")
    
    def _save_cookie(self, cookie_content: str) -> bool:
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
    
    def get_client(self, force_refresh: bool = False) -> P115Client:
        """获取115客户端实例（线程安全）"""
        with self._client_lock:
            if self._client is None or force_refresh:
                try:
                    cookie_str = self._load_cookie()
                    self._client = P115Client(
                        cookie_str,
                        ensure_cookies=self.config.get('cookie_auto_refresh', True),
                        app="qandroid"  # 使用安卓客户端标识
                    )
                    logger.info("115客户端初始化成功")
                except Exception as e:
                    logger.error(f"115客户端初始化失败: {str(e)}")
                    raise
            return self._client
    
    def qr_login(self, output_file: Optional[str] = None, show_qr: bool = True) -> Dict:
        """扫码登录获取Cookie"""
        try:
            from p115.cmd.qrcode import main as qr_main
            import sys
            from io import StringIO
            
            # 准备参数
            args = []
            if output_file:
                args.extend(['-o', output_file])
            if not show_qr:
                args.append('--no-show')
            
            # 捕获输出
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture
                
                # 执行扫码登录
                result = qr_main(args)
                
                # 如果成功，读取生成的cookie文件
                if output_file and os.path.exists(output_file):
                    with open(output_file, 'r', encoding='utf-8') as f:
                        cookie_content = f.read().strip()
                    
                    # 保存到我们的cookie文件
                    self._save_cookie(cookie_content)
                    
                    # 重新初始化客户端
                    self._client = None
                    self.get_client(force_refresh=True)
                    
                    return {
                        'success': True,
                        'message': '扫码登录成功，Cookie已保存',
                        'cookie_file': self.cookie_file
                    }
                else:
                    return {
                        'success': False,
                        'message': '扫码登录失败，未生成Cookie文件'
                    }
                    
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
        except Exception as e:
            logger.error(f"扫码登录失败: {str(e)}")
            return {
                'success': False,
                'message': f'扫码登录失败: {str(e)}'
            }
    
    def set_cookie_manual(self, cookie_content: str) -> Dict:
        """手动设置Cookie"""
        try:
            if not cookie_content or not cookie_content.strip():
                return {
                    'success': False,
                    'message': 'Cookie内容不能为空'
                }
            
            # 保存Cookie
            if self._save_cookie(cookie_content):
                # 重新初始化客户端
                self._client = None
                client = self.get_client(force_refresh=True)
                
                # 验证Cookie有效性
                if self.check_login():
                    return {
                        'success': True,
                        'message': 'Cookie设置成功，登录验证通过'
                    }
                else:
                    return {
                        'success': False,
                        'message': 'Cookie设置成功，但登录验证失败，请检查Cookie是否正确'
                    }
            else:
                return {
                    'success': False,
                    'message': 'Cookie保存失败'
                }
                
        except Exception as e:
            logger.error(f"设置Cookie失败: {str(e)}")
            return {
                'success': False,
                'message': f'设置Cookie失败: {str(e)}'
            }
    
    def check_login(self, force_check: bool = False) -> bool:
        """检查登录状态"""
        current_time = time.time()
        
        # 缓存检查（5分钟内有效）
        if not force_check and self._login_cache['valid'] and \
           (current_time - self._login_cache['last_check']) < 300:
            return True
        
        try:
            client = self.get_client()
            
            # 使用 python-115 库的方法检查登录状态
            user_info = client.user_info()
            is_valid = user_info.get('state', False)
            
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
    
    def get_folders(self, parent_id: Union[int, str] = 0, force_refresh: bool = False) -> List[Dict]:
        """获取文件夹列表"""
        try:
            # 首先检查登录状态
            if not self.check_login(force_check=force_refresh):
                logger.error("115登录状态无效，无法获取文件夹列表")
                return []
            
            client = self.get_client()
            fs = client.fs
            
            # 尝试使用iterdir方法获取完整的文件对象
            folders = []
            try:
                # 使用iterdir获取P115Path对象
                all_items = list(fs.iterdir(parent_id))
                logger.debug(f"使用iterdir从目录 {parent_id} 获取到 {len(all_items)} 个项目")
                
                for i, item in enumerate(all_items):
                    try:
                        logger.debug(f"处理项目 {i+1}: type={type(item)}, item={item}")
                        
                        # 检查是否是目录
                        if hasattr(item, 'is_dir') and callable(getattr(item, 'is_dir')):
                            if item.is_dir():
                                folder_info = {
                                    'id': str(getattr(item, 'id', '')),
                                    'name': str(getattr(item, 'name', str(item))),
                                    'path': str(getattr(item, 'path', ''))
                                }
                                folders.append(folder_info)
                                logger.debug(f"添加文件夹: {folder_info}")
                        elif hasattr(item, 'is_directory') and item.is_directory:
                            folder_info = {
                                'id': str(getattr(item, 'id', getattr(item, 'fid', ''))),
                                'name': str(getattr(item, 'name', str(item))),
                                'path': str(getattr(item, 'path', getattr(item, 'name', '')))
                            }
                            folders.append(folder_info)
                            logger.debug(f"添加文件夹(is_directory): {folder_info}")
                        else:
                            # 输出对象的所有属性以便调试
                            attrs = [attr for attr in dir(item) if not attr.startswith('_')]
                            logger.debug(f"项目属性: {attrs}")
                            if hasattr(item, '__dict__'):
                                logger.debug(f"项目__dict__: {item.__dict__}")
                    
                    except Exception as item_error:
                        logger.warning(f"处理文件夹项目时出错: {str(item_error)}, item: {item}")
                        continue
                        
            except Exception as iterdir_error:
                logger.warning(f"iterdir方法失败: {str(iterdir_error)}，尝试使用listdir")
                
                # 回退到listdir方法，但需要额外获取文件夹信息
                folder_names = list(fs.listdir(parent_id))
                logger.debug(f"使用listdir从目录 {parent_id} 获取到 {len(folder_names)} 个项目名称")
                
                # 对于每个名称，尝试获取详细信息
                for i, name in enumerate(folder_names):
                    try:
                        logger.debug(f"处理项目 {i+1}: name={name}")
                        
                        # 尝试通过路径获取对象
                        try:
                            item_path = f"/{name}" if parent_id == 0 else f"{parent_id}/{name}"
                            item = fs[item_path]
                            logger.debug(f"通过路径获取对象: type={type(item)}, item={item}")
                            
                            if hasattr(item, 'is_dir') and callable(getattr(item, 'is_dir')):
                                if item.is_dir():
                                    folder_info = {
                                        'id': str(getattr(item, 'id', '')),
                                        'name': str(getattr(item, 'name', name)),
                                        'path': str(getattr(item, 'path', name))
                                    }
                                    folders.append(folder_info)
                                    logger.debug(f"添加文件夹(路径方式): {folder_info}")
                            elif hasattr(item, 'is_directory') and item.is_directory:
                                folder_info = {
                                    'id': str(getattr(item, 'id', getattr(item, 'fid', ''))),
                                    'name': str(getattr(item, 'name', name)),
                                    'path': str(getattr(item, 'path', name))
                                }
                                folders.append(folder_info)
                                logger.debug(f"添加文件夹(路径方式is_directory): {folder_info}")
                        except Exception as path_error:
                            logger.debug(f"通过路径获取对象失败: {str(path_error)}")
                            # 假设所有listdir返回的都是文件夹（这是一个临时解决方案）
                            folder_info = {
                                'id': '',  # 无法获取ID
                                'name': str(name),
                                'path': str(name)
                            }
                            folders.append(folder_info)
                            logger.debug(f"添加文件夹(假设方式): {folder_info}")
                            
                    except Exception as item_error:
                        logger.warning(f"处理文件夹项目时出错: {str(item_error)}, name: {name}")
                        continue
            
            logger.info(f"成功获取文件夹列表，共{len(folders)}个文件夹")
            return folders
            
        except Exception as e:
            logger.error(f"获取文件夹列表失败: {str(e)}")
            return []
    
    def submit_batch_magnets(self, magnet_links: List[str], 
                           progress_callback: Optional[Callable] = None,
                           target_dir_id: Optional[Union[int, str]] = None) -> Dict:
        """批量提交磁力链接到115离线下载"""
        if not magnet_links:
            return {
                'success': True, 
                'total': 0, 
                'success_count': 0, 
                'failed_count': 0, 
                'message': '没有磁力链接需要处理'
            }
        
        logger.info(f"开始批量提交 {len(magnet_links)} 个磁力链接")
        
        try:
            client = self.get_client()
            offline = client.offline
            
            # 确定目标目录
            if target_dir_id is None:
                target_dir_id = self.config.get('target_dir_id')
            
            # 过滤有效的磁力链接
            valid_magnets = [link for link in magnet_links if self._is_valid_magnet(link)]
            if len(valid_magnets) != len(magnet_links):
                logger.warning(f"过滤掉 {len(magnet_links) - len(valid_magnets)} 个无效磁力链接")
            
            if not valid_magnets:
                return {
                    'success': False,
                    'total': len(magnet_links),
                    'success_count': 0,
                    'failed_count': len(magnet_links),
                    'message': '没有有效的磁力链接'
                }
            
            # 分批处理
            batch_size = self.config.get('batch_size', 50)
            total_success = 0
            total_failed = 0
            failed_details = []
            
            for i in range(0, len(valid_magnets), batch_size):
                batch = valid_magnets[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                total_batches = (len(valid_magnets) + batch_size - 1) // batch_size
                
                logger.info(f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch)} 个磁力链接")
                
                try:
                    # 使用 python-115 库的批量添加功能
                    result = offline.add(
                        batch,
                        pid=int(target_dir_id) if target_dir_id else None
                    )
                    
                    if result.get("state"):
                        # 批量提交成功
                        total_success += len(batch)
                        for magnet_link in batch:
                            self._processed_magnets.add(magnet_link)
                            self._save_success_record(magnet_link)
                        logger.info(f"第 {batch_num} 批提交成功: {len(batch)} 个磁力链接")
                    else:
                        # 批量提交失败，尝试逐个提交
                        logger.warning(f"第 {batch_num} 批批量提交失败，尝试逐个提交")
                        individual_result = self._submit_magnets_individually(
                            batch, offline, target_dir_id
                        )
                        total_success += individual_result['success_count']
                        total_failed += individual_result['failed_count']
                        if individual_result.get('failed_details'):
                            failed_details.extend(individual_result['failed_details'])
                    
                    # 更新进度
                    if progress_callback:
                        processed = min(i + batch_size, len(valid_magnets))
                        progress = int((processed / len(valid_magnets)) * 100)
                        progress_callback(
                            progress, 
                            f"已处理 {processed}/{len(valid_magnets)} 个磁力链接 (第 {batch_num}/{total_batches} 批)"
                        )
                    
                    # 批次间延迟
                    if batch_num < total_batches:
                        time.sleep(self.config.get('request_interval', 2))
                        
                except Exception as e:
                    logger.error(f"第 {batch_num} 批处理异常: {str(e)}，尝试逐个提交")
                    individual_result = self._submit_magnets_individually(
                        batch, offline, target_dir_id
                    )
                    total_success += individual_result['success_count']
                    total_failed += individual_result['failed_count']
                    if individual_result.get('failed_details'):
                        failed_details.extend(individual_result['failed_details'])
            
            result = {
                'success': True,
                'total': len(valid_magnets),
                'success_count': total_success,
                'failed_count': total_failed,
                'message': f"批量提交完成: 成功 {total_success} 个, 失败 {total_failed} 个"
            }
            
            if failed_details:
                result['failed_details'] = failed_details
            
            logger.info(result['message'])
            return result
            
        except Exception as e:
            logger.error(f"批量提交异常: {str(e)}")
            return {
                'success': False,
                'total': len(magnet_links),
                'success_count': 0,
                'failed_count': len(magnet_links),
                'message': f'批量提交失败: {str(e)}'
            }
    
    def _submit_magnets_individually(self, magnet_links: List[str], 
                                   offline, target_dir_id: Optional[Union[int, str]]) -> Dict:
        """逐个提交磁力链接（回退模式）"""
        logger.info(f"使用逐个提交模式处理 {len(magnet_links)} 个磁力链接")
        
        success_count = 0
        failed_count = 0
        failed_details = []
        
        for magnet_link in magnet_links:
            try:
                result = offline.add(
                    magnet_link,
                    pid=int(target_dir_id) if target_dir_id else None
                )
                
                if result.get("state"):
                    success_count += 1
                    self._processed_magnets.add(magnet_link)
                    self._save_success_record(magnet_link)
                else:
                    failed_count += 1
                    error_msg = result.get("error_msg", "未知错误")
                    failed_details.append({
                        'magnet': self._get_magnet_name(magnet_link),
                        'error': error_msg
                    })
                
                # 请求间隔
                time.sleep(self.config.get('request_interval', 2))
                
            except Exception as e:
                failed_count += 1
                failed_details.append({
                    'magnet': self._get_magnet_name(magnet_link),
                    'error': str(e)
                })
        
        return {
            'success_count': success_count,
            'failed_count': failed_count,
            'failed_details': failed_details
        }
    
    def get_offline_tasks(self, page: int = 0) -> List[Dict]:
        """获取离线任务列表"""
        try:
            client = self.get_client()
            offline = client.offline
            
            tasks = offline.list(page=page)
            
            return [{
                'name': task.get('name', ''),
                'status': task.get('status_message', ''),
                'progress': task.get('percentDone', 0),
                'info_hash': task.get('info_hash', ''),
                'size': task.get('size', 0),
                'add_time': task.get('add_time', '')
            } for task in tasks]
            
        except Exception as e:
            logger.error(f"获取离线任务失败: {str(e)}")
            return []
    
    def remove_offline_task(self, info_hash: str, remove_files: bool = False) -> bool:
        """删除离线任务"""
        try:
            client = self.get_client()
            offline = client.offline
            
            result = offline.remove(info_hash, remove_files=remove_files)
            return result.get("state", False)
            
        except Exception as e:
            logger.error(f"删除离线任务失败: {str(e)}")
            return False
    
    def move_files(self, source_dir_id: Union[int, str], 
                  target_dir_id: Union[int, str],
                  file_types: Optional[List[str]] = None) -> Dict:
        """移动文件夹下的所有文件到另一个文件夹"""
        try:
            client = self.get_client()
            fs = client.fs
            
            logger.info(f"开始获取源目录 {source_dir_id} 下的文件列表")
            # 使用底层的 fs_files 方法获取文件列表
            logger.info("调用 fs.fs_files() 方法")
            try:
                files_result = fs.fs_files({"cid": source_dir_id})
                logger.info(f"fs_files 返回结果类型: {type(files_result)}")
                
                # 从返回结果中提取文件列表
                if isinstance(files_result, dict) and 'data' in files_result:
                    source_items = files_result['data']
                    logger.info(f"获取到 {len(source_items)} 个文件/文件夹")
                else:
                    logger.error(f"fs_files 返回了意外的格式: {files_result}")
                    source_items = []
            except Exception as fs_files_error:
                logger.error(f"fs.fs_files() 调用失败: {type(fs_files_error).__name__}: {str(fs_files_error)}")
                import traceback
                logger.error(f"详细错误堆栈: {traceback.format_exc()}")
                raise
            
            # 检查 source_items 中每个项目的类型
            for i, item in enumerate(source_items[:3]):  # 只检查前3个
                logger.info(f"Item {i}: type={type(item)}, keys={list(item.keys()) if isinstance(item, dict) else 'not dict'}")
                if isinstance(item, dict):
                    # fs_files 返回的字段可能是 n (name), fid (file_id), ico (icon/type) 等
                    name_field = item.get('n', item.get('name', ''))
                    id_field = item.get('fid', item.get('id', ''))
                    is_dir = item.get('ico', '') == 'folder' or item.get('is_directory', False)
                    logger.info(f"Item {i} name: {name_field}, id: {id_field}, is_dir: {is_dir}")
            
            if file_types:
                # 过滤指定类型的文件
                filtered_items = []
                for item in source_items:
                    # 检查是否为文件（不是目录）
                    if isinstance(item, dict):
                        # 检查是否为目录
                        is_dir = item.get('ico', '') == 'folder' or item.get('is_directory', False)
                        if not is_dir:
                            # 安全获取文件名
                            item_name = item.get('n', item.get('name', ''))
                            file_ext = item_name.split('.')[-1].lower() if '.' in item_name else ''
                            if file_ext in file_types:
                                filtered_items.append(item)
                source_items = filtered_items
            
            if not source_items:
                return {
                    'success': True,
                    'total': 0,
                    'moved_count': 0,
                    'message': '源目录下没有需要移动的文件'
                }
            
            # 批量移动文件
            moved_count = 0
            failed_count = 0
            
            # 收集所有文件ID和文件名用于批量移动
            file_ids = []
            file_names = []
            
            for item in source_items:
                if isinstance(item, dict):
                    item_name = item.get('n', item.get('name', ''))
                    item_id = item.get('fid', item.get('id', ''))
                    if item_id:  # 只有有效ID的文件才加入批量移动
                        file_ids.append(int(item_id))
                        file_names.append(item_name)
                        logger.debug(f"准备移动文件: {item_name}, ID: {item_id}")
            
            if not file_ids:
                logger.warning("没有找到有效的文件ID，跳过移动操作")
                return {
                    'success': True,
                    'total': 0,
                    'moved_count': 0,
                    'failed_count': 0,
                    'message': '没有找到有效的文件进行移动'
                }
            
            logger.info(f"开始批量移动 {len(file_ids)} 个文件")
            
            try:
                # 使用批量移动API
                result = fs.fs_move(file_ids, target_dir_id)
                logger.info(f"批量移动返回结果: {result}")
                
                # 检查批量移动结果
                if isinstance(result, dict):
                    if result.get('state', False):
                        moved_count = len(file_ids)
                        logger.info(f"批量移动成功: {moved_count} 个文件")
                        for name in file_names:
                            logger.debug(f"成功移动文件: {name}")
                    else:
                        failed_count = len(file_ids)
                        error_msg = result.get('error', result.get('message', '未知错误'))
                        logger.error(f"批量移动失败: {error_msg}")
                        for name in file_names:
                            logger.error(f"移动文件 {name} 失败: {error_msg}")
                else:
                    failed_count = len(file_ids)
                    logger.error(f"fs_move 返回了意外的类型: {type(result)}")
                    
            except Exception as e:
                failed_count = len(file_ids)
                logger.error(f"批量移动文件失败: {str(e)}")
                import traceback
                logger.error(f"详细错误信息: {traceback.format_exc()}")
                for name in file_names:
                    logger.error(f"移动文件 {name} 失败: {str(e)}")
            
            result = {
                'success': True,
                'total': len(source_items),
                'moved_count': moved_count,
                'failed_count': failed_count,
                'message': f"文件移动完成: 成功 {moved_count} 个, 失败 {failed_count} 个"
            }
            
            logger.info(result['message'])
            return result
            
        except Exception as e:
            logger.error(f"移动文件失败: {str(e)}")
            return {
                'success': False,
                'total': 0,
                'moved_count': 0,
                'failed_count': 0,
                'message': f'移动文件失败: {str(e)}'
            }
    
    def start_auto_move_scheduler(self) -> bool:
        """启动定时文件移动任务"""
        if not self.config.get('auto_move_enabled', False):
            logger.info("定时文件移动功能未启用")
            return False
        
        if self._scheduler_running:
            logger.info("定时任务已在运行中")
            return True
        
        try:
            # 清除之前的任务
            schedule.clear()
            
            # 设置定时任务 - 支持cron表达式
            cron_expression = self.config.get('auto_move_cron', '0 2 * * *')  # 默认每天凌晨2点
            
            # 解析cron表达式 (简化版: 分 时 日 月 周)
            try:
                parts = cron_expression.split()
                if len(parts) == 5:
                    minute, hour, day, month, weekday = parts
                    
                    # 根据cron表达式设置schedule任务
                    if weekday != '*':
                        # 按周执行
                        weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
                        if weekday.isdigit() and 0 <= int(weekday) <= 6:
                            schedule.every().week.at(f"{hour}:{minute}").do(self._auto_move_task)
                    elif day != '*':
                        # 按月执行（简化为每月1号）
                        if day == '1':
                            schedule.every().month.do(self._auto_move_task)
                    elif hour != '*' and minute != '*':
                        # 每天指定时间执行
                        schedule.every().day.at(f"{hour}:{minute}").do(self._auto_move_task)
                    else:
                        # 默认每24小时执行一次
                        schedule.every(24).hours.do(self._auto_move_task)
                else:
                    # 如果cron格式不正确，使用小时间隔模式
                    interval_hours = self.config.get('auto_move_interval_hours', 24)
                    schedule.every(interval_hours).hours.do(self._auto_move_task)
                    
            except Exception as cron_error:
                logger.warning(f"解析cron表达式失败: {cron_error}，使用默认间隔模式")
                interval_hours = self.config.get('auto_move_interval_hours', 24)
                schedule.every(interval_hours).hours.do(self._auto_move_task)
            
            # 启动调度器线程
            self._scheduler_running = True
            self._scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
            self._scheduler_thread.start()
            
            logger.info(f"定时文件移动任务已启动，cron表达式: {cron_expression}")
            return True
            
        except Exception as e:
            logger.error(f"启动定时任务失败: {str(e)}")
            return False
    
    def stop_auto_move_scheduler(self) -> bool:
        """停止定时文件移动任务"""
        try:
            self._scheduler_running = False
            schedule.clear()
            
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                self._scheduler_thread.join(timeout=5)
            
            logger.info("定时文件移动任务已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止定时任务失败: {str(e)}")
            return False
    
    def _run_scheduler(self):
        """运行调度器"""
        while self._scheduler_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"调度器运行异常: {str(e)}")
                time.sleep(60)
    
    def _auto_move_task(self):
        """自动移动文件任务"""
        try:
            source_dir_id = self.config.get('auto_move_source_dir_id')
            target_dir_id = self.config.get('auto_move_target_dir_id')
            
            if not source_dir_id or not target_dir_id:
                logger.warning("定时移动任务配置不完整，跳过执行")
                return
            
            logger.info("开始执行定时文件移动任务")
            result = self.move_files(source_dir_id, target_dir_id)
            
            if result['success']:
                logger.info(f"定时移动任务完成: {result['message']}")
            else:
                logger.error(f"定时移动任务失败: {result['message']}")
                
        except Exception as e:
            logger.error(f"定时移动任务异常: {str(e)}")
    
    def manual_move_files(self) -> dict:
        """手动触发文件移动"""
        try:
            source_dir_id = self.config.get('auto_move_source_dir_id')
            target_dir_id = self.config.get('auto_move_target_dir_id')
            
            if not source_dir_id or not target_dir_id:
                return {
                    'success': False,
                    'message': '源文件夹ID或目标文件夹ID未配置'
                }
            
            logger.info("开始执行手动文件移动任务")
            result = self.move_files(source_dir_id, target_dir_id)
            
            if result['success']:
                logger.info(f"手动移动任务完成: {result['message']}")
            else:
                logger.error(f"手动移动任务失败: {result['message']}")
            
            return result
                
        except Exception as e:
            error_msg = f"手动移动任务执行异常: {str(e)}"
            logger.error(error_msg)
            return {
                'success': False,
                'message': error_msg
            }
    
    def get_storage_info(self) -> Dict:
        """获取存储空间信息"""
        try:
            client = self.get_client()
            info = client.user_info()
            
            return {
                'total_space': info.get('total_space', 0),
                'used_space': info.get('used_space', 0),
                'free_space': info.get('free_space', 0),
                'username': info.get('username', ''),
                'user_id': info.get('user_id', '')
            }
            
        except Exception as e:
            logger.error(f"获取存储信息失败: {str(e)}")
            return {}
    
    def get_offline_quota_info(self) -> Dict:
        """获取离线下载配额信息"""
        try:
            client = self.get_client()
            offline = client.offline
            
            quota_info = offline.quota_info
            
            return {
                'quota': quota_info.get('quota', 0),
                'total': quota_info.get('total', 0),
                'used': quota_info.get('used', 0),
                'remaining': quota_info.get('quota', 0) - quota_info.get('used', 0)
            }
            
        except Exception as e:
            logger.error(f"获取离线配额信息失败: {str(e)}")
            return {}
    
    def _is_valid_magnet(self, magnet_link: str) -> bool:
        """检查磁力链接是否有效"""
        if not magnet_link or not isinstance(magnet_link, str):
            return False
        
        magnet_link = magnet_link.strip()
        if not magnet_link.startswith("magnet:?"):
            return False
        
        try:
            magnet_link.encode('utf-8')
            if 'xt=' not in magnet_link:
                return False
            return True
        except UnicodeEncodeError:
            return False
    
    def _get_magnet_name(self, magnet_link: str) -> str:
        """从磁力链接中提取文件名"""
        try:
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(magnet_link).query)
            return query.get("dn", ["磁力链接"])[0][:50] + "..."
        except:
            return magnet_link[:30] + "..."
    
    def _save_success_record(self, magnet_link: str):
        """保存成功转存记录"""
        try:
            os.makedirs(os.path.dirname(self.success_record_file), exist_ok=True)
            with open(self.success_record_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp}\t{self._get_magnet_name(magnet_link)}\t{magnet_link}\n")
        except Exception as e:
            logger.error(f"保存成功记录失败: {str(e)}")
    
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
                    import pandas as pd
                    df = pd.read_csv(current_csv_file)
                    if magnet_column in df.columns:
                        self.processed_magnets = set(df[magnet_column].dropna().astype(str).tolist())
                        logger.info(f"从当前CSV文件加载了 {len(self.processed_magnets)} 个磁力链接用于去重")
                    else:
                        logger.warning(f"CSV文件中未找到磁力链接列: {magnet_column}")
                        self.processed_magnets = set()
                except Exception as e:
                    logger.error(f"读取当前CSV文件失败: {str(e)}")
                    self.processed_magnets = set()
            else:
                # 全局去重（从历史记录文件加载）
                if os.path.exists(self.success_record_file):
                    with open(self.success_record_file, 'r', encoding='utf-8') as f:
                        self.processed_magnets = set()
                        for line in f:
                            parts = line.strip().split('\t')
                            if len(parts) >= 3:
                                self.processed_magnets.add(parts[2])
                    logger.info(f"从历史记录加载了 {len(self.processed_magnets)} 个已处理的磁力链接")
                else:
                    self.processed_magnets = set()
                    logger.info("未找到历史记录文件，将创建新的记录")
        except Exception as e:
            logger.error(f"加载已处理磁力链接失败: {str(e)}")
            self.processed_magnets = set()
    
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
        
        try:
            import pandas as pd
            df = pd.read_csv(csv_file)
            
            if magnet_column not in df.columns:
                raise ValueError(f"CSV文件中未找到磁力链接列: {magnet_column}")
            
            # 提取有效的磁力链接
            magnet_links = []
            for magnet in df[magnet_column].dropna():
                magnet_str = str(magnet).strip()
                if self._is_valid_magnet(magnet_str):
                    # 去重检查
                    if self.config.get('skip_duplicates', True) and magnet_str in self.processed_magnets:
                        logger.debug(f"跳过重复磁力链接: {self._get_magnet_name(magnet_str)}")
                        continue
                    magnet_links.append(magnet_str)
            
            if not magnet_links:
                logger.info("CSV文件中没有找到新的有效磁力链接")
                return {'success': True, 'message': 'CSV文件中没有找到新的有效磁力链接', 'total': 0, 'success_count': 0, 'failed_count': 0}
            
            logger.info(f"从CSV文件提取到 {len(magnet_links)} 个有效磁力链接")
            
            # 批量提交磁力链接
            result = self.submit_batch_magnets(magnet_links, progress_callback)
            
            # 保存成功的磁力链接记录
            if result.get('success') and result.get('success_count', 0) > 0:
                for magnet in magnet_links[:result.get('success_count', 0)]:
                    self._save_success_record(magnet)
            
            return result
            
        except Exception as e:
            logger.error(f"处理CSV文件失败: {str(e)}")
            raise
    
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
        
        try:
            import pandas as pd
            df = pd.read_csv(csv_file)
            
            if magnet_column not in df.columns:
                raise ValueError(f"CSV文件中未找到磁力链接列: {magnet_column}")
            
            # 提取有效的磁力链接
            valid_magnets = []
            duplicate_count = 0
            invalid_count = 0
            
            for magnet in df[magnet_column].dropna():
                magnet_str = str(magnet).strip()
                
                if not self._is_valid_magnet(magnet_str):
                    invalid_count += 1
                    continue
                
                # 去重检查
                if self.config.get('skip_duplicates', True) and magnet_str in self.processed_magnets:
                    duplicate_count += 1
                    logger.debug(f"跳过重复磁力链接: {self._get_magnet_name(magnet_str)}")
                    continue
                
                valid_magnets.append(magnet_str)
            
            # 保存到缓存文件
            with open(cache_file, 'w', encoding='utf-8') as f:
                for magnet in valid_magnets:
                    f.write(magnet + '\n')
            
            result = {
                'success': True,
                'cache_file': cache_file,
                'total_count': len(df),
                'cached_count': len(valid_magnets),
                'duplicate_count': duplicate_count,
                'invalid_count': invalid_count,
                'message': f'成功提取 {len(valid_magnets)} 个磁力链接到缓存文件'
            }
            
            logger.info(f"磁力链接提取完成: 总数={len(df)}, 有效={len(valid_magnets)}, 重复={duplicate_count}, 无效={invalid_count}")
            return result
            
        except Exception as e:
            logger.error(f"提取磁力链接到缓存失败: {str(e)}")
            raise
    
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
        
        logger.info(f"从缓存文件读取到 {len(magnets)} 个磁力链接，将分 {(len(magnets) + batch_size - 1) // batch_size} 批处理")
        
        total_success = 0
        total_failed = 0
        total_batches = (len(magnets) + batch_size - 1) // batch_size
        
        for i in range(0, len(magnets), batch_size):
            batch_magnets = magnets[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_magnets)} 个磁力链接")
            
            try:
                # 使用批量提交
                result = self.submit_batch_magnets(batch_magnets)
                
                if result.get('success'):
                    batch_success = result.get('success_count', 0)
                    batch_failed = result.get('failed_count', 0)
                    total_success += batch_success
                    total_failed += batch_failed
                    
                    # 保存成功的记录
                    for magnet in batch_magnets[:batch_success]:
                        self._save_success_record(magnet)
                    
                    logger.info(f"第 {batch_num} 批处理完成: 成功 {batch_success}, 失败 {batch_failed}")
                else:
                    total_failed += len(batch_magnets)
                    logger.error(f"第 {batch_num} 批处理失败: {result.get('message', '未知错误')}")
                
                # 进度回调
                if progress_callback:
                    progress = (batch_num / total_batches) * 100
                    progress_callback({
                        'progress': progress,
                        'current_batch': batch_num,
                        'total_batches': total_batches,
                        'success_count': total_success,
                        'failed_count': total_failed
                    })
                
                # 批次间延迟
                if batch_num < total_batches:
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"第 {batch_num} 批处理异常: {str(e)}")
                total_failed += len(batch_magnets)
        
        result = {
            'success': True,
            'total_batches': total_batches,
            'total_magnets': len(magnets),
            'success_count': total_success,
            'failed_count': total_failed,
            'message': f'缓存处理完成: 成功 {total_success}, 失败 {total_failed}'
        }
        
        logger.info(f"缓存文件处理完成: 总计 {len(magnets)} 个磁力链接，成功 {total_success}, 失败 {total_failed}")
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
                    'cache_result': cache_result,
                    'process_result': None,
                    'message': '没有新的磁力链接需要处理'
                }
            
            # 第二步：分批处理缓存文件
            logger.info("第二步：分批处理缓存文件中的磁力链接")
            cache_file = cache_result['cache_file']
            process_result = self.process_cache_file(cache_file, batch_size, progress_callback)
            
            return {
                'success': True,
                'cache_result': cache_result,
                'process_result': process_result,
                'message': f'缓存处理完成: 提取 {cache_result["cached_count"]} 个，成功转存 {process_result.get("success_count", 0)} 个'
            }
            
        except Exception as e:
            logger.error(f"使用缓存处理CSV文件失败: {str(e)}")
            raise
    
    def cleanup(self):
        """清理资源"""
        try:
            self.stop_auto_move_scheduler()
            logger.info("Pan115Manager 资源清理完成")
        except Exception as e:
            logger.error(f"资源清理失败: {str(e)}")
    
    def __del__(self):
        """析构函数"""
        self.cleanup()


    def manual_transfer_csv(self, csv_file, progress_callback=None):
        """手动转存CSV文件中的磁力链接"""
        try:
            logger.info(f"开始手动转存CSV文件: {csv_file}")
            
            # 使用缓存机制处理，强制转存（跳过自动转存开关检查）
            result = self.process_csv_with_cache(
                csv_file=csv_file,
                batch_size=self.config.get('batch_size', 100),
                progress_callback=progress_callback,
                force_transfer=True  # 手动转存时强制执行
            )
            
            if result['success']:
                cache_result = result.get('cache_result', {})
                process_result = result.get('process_result', {})
                
                return {
                    'success': True,
                    'message': f'手动转存完成: 提取 {cache_result.get("cached_count", 0)} 个磁力链接，成功转存 {process_result.get("success_count", 0) if process_result else 0} 个',
                    'total_extracted': cache_result.get('cached_count', 0),
                    'total_success': process_result.get('success_count', 0) if process_result else 0,
                    'total_failed': process_result.get('failed_count', 0) if process_result else 0,
                    'cache_file': cache_result.get('cache_file', ''),
                    'duplicate_count': cache_result.get('duplicate_count', 0),
                    'invalid_count': cache_result.get('invalid_count', 0)
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', '手动转存失败'),
                    'error': result.get('message', '未知错误')
                }
                
        except Exception as e:
            logger.error(f"手动转存CSV文件失败: {str(e)}")
            return {
                'success': False,
                'message': f'手动转存失败: {str(e)}',
                'error': str(e)
            }


# 使用示例
if __name__ == "__main__":
    # 创建管理器实例
    manager = Pan115Manager()
    
    # 扫码登录
    # result = manager.qr_login(output_file="temp_cookie.txt")
    # print(result)
    
    # 手动设置Cookie
    # cookie = "your_cookie_here"
    # result = manager.set_cookie_manual(cookie)
    # print(result)
    
    # 检查登录状态
    # if manager.check_login():
    #     print("登录成功")
    #     
    #     # 批量提交磁力链接
    #     magnets = ["magnet:?xt=urn:btih:example1", "magnet:?xt=urn:btih:example2"]
    #     result = manager.submit_batch_magnets(magnets)
    #     print(result)
    #     
    #     # 获取离线任务
    #     tasks = manager.get_offline_tasks()
    #     print(f"离线任务数量: {len(tasks)}")
    #     
    #     # 启动定时移动任务
    #     manager.start_auto_move_scheduler()
    # else:
    #     print("登录失败")