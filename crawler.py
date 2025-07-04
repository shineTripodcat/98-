#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import csv
import time
import random
import logging
import threading
from datetime import datetime
from typing import List, Dict, Any, Callable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
# from webdriver_manager.chrome import ChromeDriverManager  # 不再使用webdriver-manager
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class WebCrawler:
    """Web爬虫类"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        
        # 处理嵌套配置结构，优先使用basic节点下的配置
        basic_config = config.get('basic', {})
        
        self.base_url = basic_config.get('base_url') or config.get('base_url', 'https://s9ko.avp76.net')
        self.data_dir = config.get('data_dir', './data')
        self.worker_count = basic_config.get('worker_count') or config.get('worker_count', 5)
        self.min_wait_time = basic_config.get('min_wait_time') or config.get('min_wait_time', 2)
        self.random_delay = basic_config.get('random_delay') or config.get('random_delay', 5)
        self.headless = basic_config.get('headless') if basic_config.get('headless') is not None else config.get('headless', True)
        self.debug = basic_config.get('debug') if basic_config.get('debug') is not None else config.get('debug', False)
        
        # 代理配置（重要修复）
        self.proxy = basic_config.get('proxy') or config.get('proxy', '')
        self.user_agent = basic_config.get('user_agent') or config.get('user_agent', '')
        
        logger.info(f"代理配置: {self.proxy if self.proxy else '未设置'}")
        logger.info(f"用户代理: {self.user_agent[:50]}..." if self.user_agent else "用户代理: 未设置")
        
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 线程锁
        self._lock = threading.Lock()
        
        # 停止标志函数（由外部设置）
        self.stop_flag = lambda: False
        
        # 统计信息
        self.stats = {
            'total_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'start_time': None,
            'end_time': None
        }
    
    def _create_driver(self) -> webdriver.Chrome:
        """创建Chrome驱动"""
        options = Options()
        
        # 基本选项
        if self.headless:
            options.add_argument('--headless')
        
        # Docker环境的必要选项
        if os.path.exists('/.dockerenv') or os.environ.get('MICRO_ENV'):
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')
            options.add_argument('--disable-javascript')
            options.add_argument('--disable-css')
            # 添加网络稳定性选项
            options.add_argument('--disable-background-timer-throttling')
            options.add_argument('--disable-backgrounding-occluded-windows')
            options.add_argument('--disable-renderer-backgrounding')
            options.add_argument('--disable-features=TranslateUI')
            options.add_argument('--disable-ipc-flooding-protection')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-default-apps')
            options.add_argument('--disable-sync')
            # 网络连接优化
            options.add_argument('--aggressive-cache-discard')
            options.add_argument('--max_old_space_size=4096')
            logger.info("已添加Docker环境优化选项")
        
        # 添加Chrome选项
        chrome_options = self.config.get('chrome_options', [])
        for option in chrome_options:
            options.add_argument(option)
        
        # 设置用户代理
        if self.user_agent:
            options.add_argument(f'--user-agent={self.user_agent}')
            logger.info(f"设置用户代理: {self.user_agent[:50]}...")
        
        # 设置代理（重要修复）
        if self.proxy:
            options.add_argument(f'--proxy-server={self.proxy}')
            logger.info(f"设置代理服务器: {self.proxy}")
        
        # 设置Chrome路径
        chrome_path = self.config.get('chrome_path', '')
        if chrome_path and os.path.exists(chrome_path):
            options.binary_location = chrome_path
            logger.info(f"使用配置文件指定的Chrome路径: {chrome_path}")
        elif os.environ.get('CHROME_BIN'):
            chrome_bin = os.environ.get('CHROME_BIN')
            if os.path.exists(chrome_bin):
                options.binary_location = chrome_bin
                logger.info(f"使用环境变量指定的Chrome路径: {chrome_bin}")
        
        try:
            # 检测运行环境并设置ChromeDriver路径
            chromedriver_path = None
            
            # 优先使用环境变量指定的路径
            if os.environ.get('CHROMEDRIVER_PATH'):
                chromedriver_path = os.environ.get('CHROMEDRIVER_PATH')
                logger.info(f"使用环境变量指定的ChromeDriver路径: {chromedriver_path}")
            # 检查是否为Docker环境
            elif os.path.exists('/.dockerenv'):
                chromedriver_path = '/usr/bin/chromedriver'
                logger.info(f"检测到Docker环境，使用路径: {chromedriver_path}")
            # Linux环境（备用检查）
            elif os.path.exists('/usr/bin/chromedriver'):
                chromedriver_path = '/usr/bin/chromedriver'
                logger.info(f"检测到Linux环境，使用路径: {chromedriver_path}")
            # Windows环境
            else:
                current_dir = os.path.dirname(os.path.abspath(__file__))
                chromedriver_path = os.path.join(current_dir, 'drivers', 'chromedriver-win64', 'chromedriver.exe')
                logger.info(f"检测到Windows环境，使用路径: {chromedriver_path}")
            
            if not os.path.exists(chromedriver_path):
                logger.error(f"ChromeDriver文件不存在: {chromedriver_path}")
                logger.error(f"环境变量CHROMEDRIVER_PATH: {os.environ.get('CHROMEDRIVER_PATH')}")
                logger.error(f"环境变量MICRO_ENV: {os.environ.get('MICRO_ENV')}")
                logger.error(f"Docker环境检查: {os.path.exists('/.dockerenv')}")
                raise FileNotFoundError(f"ChromeDriver文件不存在: {chromedriver_path}")
            
            service = webdriver.chrome.service.Service(chromedriver_path)
            driver = webdriver.Chrome(service=service, options=options)
            
            # 设置超时
            driver.set_page_load_timeout(30)
            driver.implicitly_wait(10)
            
            return driver
        
        except Exception as e:
            logger.error(f"创建Chrome驱动失败: {str(e)}")
            raise
    
    def _handle_age_verification(self, driver: webdriver.Chrome) -> bool:
        """处理年龄验证"""
        try:
            logger.info("检查年龄验证...")
            
            # 查找年龄确认按钮
            try:
                # 等待页面加载
                time.sleep(2)
                
                # 查找包含"满18岁"的按钮
                buttons = driver.find_elements(By.CSS_SELECTOR, 'a.enter-btn')
                
                for button in buttons:
                    if '满18岁' in button.text:
                        logger.info("找到年龄确认按钮，正在点击...")
                        button.click()
                        time.sleep(3)  # 等待页面跳转
                        return True
                
                logger.info("未找到年龄确认按钮")
                return True
                
            except Exception as e:
                logger.debug(f"年龄验证处理异常: {str(e)}")
                return True
        
        except Exception as e:
            logger.error(f"处理年龄验证失败: {str(e)}")
            return False
    
    def _get_page_tids(self, driver: webdriver.Chrome, page_url: str) -> List[str]:
        """获取页面中的TID列表"""
        try:
            logger.debug(f"访问页面: {page_url}")
            driver.get(page_url)
            
            # 等待页面加载
            time.sleep(random.randint(2, 4))
            
            # 获取页面源码
            html = driver.page_source
            
            # 使用正则表达式提取TID
            tid_pattern = r'mod=viewthread&(?:amp;)?tid=(\d+)'
            matches = re.findall(tid_pattern, html)
            
            # 去重并返回
            unique_tids = list(set(matches))
            logger.debug(f"页面 {page_url} 找到 {len(unique_tids)} 个TID")
            
            return unique_tids
        
        except Exception as e:
            logger.error(f"获取页面TID失败 {page_url}: {str(e)}")
            return []
    
    def _crawl_page_magnets(self, driver: webdriver.Chrome, tid: str, forum_id: str) -> Dict[str, Any]:
        """爬取单个页面的磁力链接"""
        url = f"{self.base_url}/forum.php?mod=viewthread&tid={tid}"
        
        result = {
            'tid': tid,
            'url': url,
            'forum_id': forum_id,
            'title': '',
            'magnets': [],
            'success': False,
            'message': '',
            'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            logger.debug(f"访问TID页面: {tid}")
            driver.get(url)
            
            # 等待页面加载
            time.sleep(random.randint(2, 4))
            
            # 处理可能的年龄验证
            self._handle_age_verification(driver)
            
            # 获取页面标题
            try:
                result['title'] = driver.title
            except:
                result['title'] = f"TID_{tid}"
            
            # 获取页面源码
            html = driver.page_source
            
            # 提取磁力链接
            magnets = self._extract_magnets(html)
            result['magnets'] = magnets
            
            if magnets:
                result['success'] = True
                result['message'] = f"成功提取 {len(magnets)} 个磁力链接"
                logger.debug(f"TID {tid} 成功提取 {len(magnets)} 个磁力链接")
            else:
                result['message'] = "未找到磁力链接"
                logger.debug(f"TID {tid} 未找到磁力链接")
            
            return result
        
        except Exception as e:
            result['message'] = f"页面处理失败: {str(e)}"
            logger.error(f"爬取TID {tid} 失败: {str(e)}")
            return result
    
    def _extract_magnets(self, html: str) -> List[str]:
        """从HTML中提取磁力链接"""
        try:
            # 磁力链接正则表达式
            magnet_pattern = r'magnet:\?xt=urn:btih:[0-9a-zA-Z]{32,50}[^\s"<>]*'
            magnets = re.findall(magnet_pattern, html, re.IGNORECASE)
            
            # 去重并标准化
            unique_magnets = []
            seen = set()
            
            for magnet in magnets:
                # 标准化磁力链接
                magnet = magnet.lower().strip()
                if magnet not in seen:
                    unique_magnets.append(magnet)
                    seen.add(magnet)
            
            return unique_magnets
        
        except Exception as e:
            logger.error(f"提取磁力链接失败: {str(e)}")
            return []
    
    def _save_tids_to_file(self, tids: List[str], filename: str) -> bool:
        """保存TID到文件"""
        try:
            # 如果filename已经包含路径，直接使用；否则拼接data_dir
            if os.path.dirname(filename):
                filepath = filename
            else:
                filepath = os.path.join(self.data_dir, filename)
            
            # 确保目录存在
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # 去重并排序（从大到小）
            unique_tids = list(set(tids))
            unique_tids.sort(key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                for tid in unique_tids:
                    f.write(f"{tid}\n")
            
            logger.info(f"成功保存 {len(unique_tids)} 个TID到 {filepath}")
            return True
        
        except Exception as e:
            logger.error(f"保存TID文件失败: {str(e)}")
            return False
    
    def _load_tids_from_file(self, filename: str) -> List[str]:
        """从文件加载TID"""
        try:
            # 如果filename已经包含路径，直接使用；否则拼接data_dir
            if os.path.dirname(filename):
                filepath = filename
            else:
                filepath = os.path.join(self.data_dir, filename)
            
            if not os.path.exists(filepath):
                logger.warning(f"TID文件不存在: {filepath}")
                return []
            
            tids = []
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    tid = line.strip()
                    if tid and tid.isdigit():
                        tids.append(tid)
            
            # 按数值排序（大的TID表示更新的帖子）
            tids.sort(key=lambda x: int(x), reverse=True)
            
            logger.info(f"从 {filepath} 加载 {len(tids)} 个TID")
            return tids
        
        except Exception as e:
            logger.error(f"加载TID文件失败: {str(e)}")
            return []
    
    def _save_results_to_csv(self, results: List[Dict[str, Any]], filename: str) -> str:
        """保存结果到CSV文件，返回完整文件路径"""
        try:
            filepath = os.path.join(self.data_dir, filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 写入表头
                headers = [
                    '论坛板块', 'TID', 'URL', '标题', '状态',
                    '消息', '磁力链接数量', '磁力链接', '爬取时间'
                ]
                writer.writerow(headers)
                
                # 写入数据
                for result in results:
                    status = '成功' if result.get('success', False) else '失败'
                    magnets_str = ';'.join(result.get('magnets', []))
                    
                    row = [
                        result.get('forum_id', ''),
                        result.get('tid', ''),
                        result.get('url', ''),
                        result.get('title', ''),
                        status,
                        result.get('message', ''),
                        len(result.get('magnets', [])),
                        magnets_str,
                        result.get('datetime', '')
                    ]
                    writer.writerow(row)
            
            logger.info(f"结果已保存到CSV文件: {filepath}")
            return filepath  # 返回完整文件路径
        
        except Exception as e:
            logger.error(f"保存CSV文件失败: {str(e)}")
            return None
    
    def _compare_tids(self, tid1: str, tid2: str) -> int:
        """比较两个TID的大小"""
        try:
            num1 = int(tid1) if tid1.isdigit() else 0
            num2 = int(tid2) if tid2.isdigit() else 0
            return num1 - num2
        except:
            return 0
    
    def crawl_forum_tids(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """爬取论坛板块获取TID"""
        logger.info("开始爬取论坛板块获取TID")
        self.stats['start_time'] = datetime.now()
        
        try:
            forums = self.config.get('forums', [])
            enabled_forums = [f for f in forums if f.get('enabled', True)]
            
            if not enabled_forums:
                return {'success': False, 'message': '没有启用的论坛配置'}
            
            all_results = []
            
            for forum_idx, forum in enumerate(enabled_forums):
                if progress_callback:
                    progress = int((forum_idx / len(enabled_forums)) * 100)
                    progress_callback(progress, f"处理论坛 {forum.get('name', 'Unknown')}")
                
                result = self._crawl_single_forum_tids(forum)
                all_results.append(result)
            
            if progress_callback:
                progress_callback(100, "TID爬取完成")
            
            self.stats['end_time'] = datetime.now()
            
            return {
                'success': True,
                'message': f"成功处理 {len(enabled_forums)} 个论坛",
                'results': all_results,
                'stats': self.stats
            }
        
        except Exception as e:
            logger.error(f"爬取论坛TID失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _crawl_single_forum_tids(self, forum: Dict[str, Any]) -> Dict[str, Any]:
        """爬取单个论坛的TID"""
        fid = forum.get('fid', '36')
        typeid = forum.get('typeid', '672')
        tid_file = forum.get('tid_file', 'tids.txt')
        start_page = forum.get('start_page', 1)
        end_page = forum.get('end_page', 100)
        
        # 限制每次爬取的页数
        max_pages = self.config.get('max_pages_per_run', 5)
        last_page = self.config.get('last_crawl_page', 0)
        
        if last_page > 0:
            start_page = last_page + 1
        
        if (end_page - start_page + 1) > max_pages:
            end_page = start_page + max_pages - 1
        
        logger.info(f"爬取论坛 FID={fid}, TypeID={typeid}, 页码范围: {start_page}-{end_page}")
        
        all_tids = []
        
        # 使用线程池爬取页面
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            futures = []
            
            for page in range(start_page, end_page + 1):
                future = executor.submit(self._crawl_forum_page, fid, typeid, page)
                futures.append((page, future))
            
            for page, future in futures:
                try:
                    tids = future.result(timeout=60)
                    all_tids.extend(tids)
                    logger.info(f"第 {page} 页找到 {len(tids)} 个TID")
                except Exception as e:
                    logger.error(f"爬取第 {page} 页失败: {str(e)}")
        
        # 保存TID到文件
        self._save_tids_to_file(all_tids, tid_file)
        
        return {
            'forum': forum,
            'total_tids': len(all_tids),
            'pages_crawled': end_page - start_page + 1,
            'last_page': end_page
        }
    
    def _crawl_forum_page(self, fid: str, typeid: str, page: int) -> List[str]:
        """爬取论坛单页"""
        driver = None
        try:
            # 随机延迟
            delay = self.min_wait_time + random.randint(0, self.random_delay)
            time.sleep(delay)
            
            driver = self._create_driver()
            
            # 首先访问首页处理年龄验证
            driver.get(self.base_url)
            self._handle_age_verification(driver)
            
            # 构造论坛页面URL
            forum_url = f"/forum.php?mod=forumdisplay&fid={fid}&filter=typeid&typeid={typeid}&page={page}"
            page_url = f"{self.base_url}{forum_url}"
            
            # 获取页面TID
            tids = self._get_page_tids(driver, page_url)
            
            return tids
        
        except Exception as e:
            logger.error(f"爬取论坛页面失败 (FID={fid}, Page={page}): {str(e)}")
            return []
        
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def crawl_magnets_full(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """全量爬取磁力链接"""
        logger.info("开始全量爬取磁力链接")
        self.stats['start_time'] = datetime.now()
        
        try:
            forums = self.config.get('forums', [])
            enabled_forums = [f for f in forums if f.get('enabled', True)]
            
            if not enabled_forums:
                return {'success': False, 'message': '没有启用的论坛配置'}
            
            all_results = []
            
            for forum_idx, forum in enumerate(enabled_forums):
                if progress_callback:
                    progress = int((forum_idx / len(enabled_forums)) * 50)
                    progress_callback(progress, f"处理论坛 {forum.get('name', 'Unknown')}")
                
                # 加载TID文件
                tid_file = forum.get('tid_file', 'tids.txt')
                tids = self._load_tids_from_file(tid_file)
                
                if not tids:
                    logger.warning(f"论坛 {forum.get('name')} 没有TID数据")
                    continue
                
                # 爬取磁力链接
                forum_id = f"{forum.get('fid')}_{forum.get('typeid')}"
                results = self._crawl_tids_magnets(tids, forum_id, progress_callback)
                all_results.extend(results)
                
                # 更新最大TID
                if tids:
                    max_tid = tids[0]  # 已经按降序排序
                    self.config['max_tid'] = max_tid
            
            # 保存结果
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"full_crawl_{timestamp}.csv"
            
            result_file = self._save_results_to_csv(all_results, filename)
            
            if progress_callback:
                progress_callback(100, "全量爬取完成")
            
            self.stats['end_time'] = datetime.now()
            
            return {
                'success': True,
                'message': f"全量爬取完成，处理 {len(all_results)} 个TID",
                'total_processed': len(all_results),
                'success_count': sum(1 for r in all_results if r.get('success')),
                'result_file': result_file,
                'max_tid': self.config.get('max_tid', '0'),
                'stats': self.stats
            }
        
        except Exception as e:
            logger.error(f"全量爬取失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def crawl_magnets_incremental(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """增量爬取磁力链接"""
        logger.info("开始增量爬取磁力链接")
        self.stats['start_time'] = datetime.now()
        
        try:
            # 检查停止标志
            if self.stop_flag():
                return {'success': False, 'message': '任务已被停止'}
                
            forums = self.config.get('forums', [])
            enabled_forums = [f for f in forums if f.get('enabled', True)]
            
            if not enabled_forums:
                return {'success': False, 'message': '没有启用的论坛配置'}
            
            max_tid = self.config.get('max_tid', '0')
            logger.info(f"当前max_tid: {max_tid}")
            
            all_results = []
            new_tids_count = 0
            
            # 第一步：先爬取最新的TID（根据配置的页数）
            logger.info("第一步：爬取最新TID...")
            for forum_idx, forum in enumerate(enabled_forums):
                # 检查停止标志
                if self.stop_flag():
                    logger.info("检测到停止信号，终止TID爬取")
                    break
                    
                if progress_callback:
                    progress = int((forum_idx / len(enabled_forums)) * 25)
                    progress_callback(progress, f"爬取论坛 {forum.get('name', 'Unknown')} 的最新TID")
                
                # 爬取最新TID
                tid_result = self._crawl_single_forum_tids(forum)
                if not tid_result.get('total_tids', 0):
                    logger.warning(f"论坛 {forum.get('name')} 未获取到新TID")
                    continue
                    
                logger.info(f"论坛 {forum.get('name')} 爬取到 {tid_result.get('total_tids', 0)} 个TID")
            
            # 第二步：加载TID文件并与max_tid对比
            logger.info("第二步：对比TID并筛选新内容...")
            for forum_idx, forum in enumerate(enabled_forums):
                # 检查停止标志
                if self.stop_flag():
                    logger.info("检测到停止信号，终止增量爬取")
                    break
                    
                if progress_callback:
                    progress = 25 + int((forum_idx / len(enabled_forums)) * 25)
                    progress_callback(progress, f"对比论坛 {forum.get('name', 'Unknown')} 的TID")
                
                # 加载TID文件
                tid_file = forum.get('tid_file', 'tids.txt')
                all_tids = self._load_tids_from_file(tid_file)
                
                if not all_tids:
                    logger.warning(f"论坛 {forum.get('name')} 没有TID数据")
                    continue
                
                logger.info(f"论坛 {forum.get('name')} 加载了 {len(all_tids)} 个TID")
                
                # 筛选新TID的逻辑：
                # 如果max_tid为'0'，表示所有TID都是新的
                # 否则，只选择大于max_tid的TID
                if max_tid == '0':
                    new_tids = all_tids.copy()  # 所有TID都是新的
                    logger.info(f"max_tid为0，论坛 {forum.get('name')} 的所有 {len(new_tids)} 个TID都被视为新TID")
                else:
                    new_tids = [tid for tid in all_tids if self._compare_tids(tid, max_tid) > 0]
                    logger.info(f"论坛 {forum.get('name')} 找到 {len(new_tids)} 个新TID (大于 {max_tid})")
                
                if not new_tids:
                    logger.info(f"论坛 {forum.get('name')} 没有新的TID需要爬取 (当前max_tid: {max_tid})")
                    continue
                
                # 确保new_tids按降序排序
                new_tids.sort(key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
                new_tids_count += len(new_tids)
                
                # 检查停止标志
                if self.stop_flag():
                    logger.info("检测到停止信号，终止爬取")
                    break
                
                # 第三步：爬取新TID的磁力链接
                forum_id = f"{forum.get('fid')}_{forum.get('typeid')}"
                results = self._crawl_tids_magnets(new_tids, forum_id, progress_callback)
                all_results.extend(results)
                
                # 更新最大TID
                if new_tids:
                    new_max_tid = new_tids[0]  # 已经按降序排序
                    if self._compare_tids(new_max_tid, max_tid) > 0:
                        max_tid = new_max_tid
            
            # 更新配置中的最大TID
            if max_tid != self.config.get('max_tid', '0'):
                self.config['max_tid'] = max_tid
            
            # 保存结果
            result_file = None
            if all_results:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"incremental_crawl_{timestamp}.csv"
                
                result_file = self._save_results_to_csv(all_results, filename)
            
            if progress_callback:
                progress_callback(100, "增量爬取完成")
            
            self.stats['end_time'] = datetime.now()
            
            return {
                'success': True,
                'message': f"增量爬取完成，发现 {new_tids_count} 个新TID，处理 {len(all_results)} 个页面",
                'new_tids_count': new_tids_count,
                'total_processed': len(all_results),
                'success_count': sum(1 for r in all_results if r.get('success')),
                'result_file': result_file if all_results else None,
                'max_tid': max_tid,
                'stats': self.stats
            }
        
        except Exception as e:
            logger.error(f"增量爬取失败: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def _crawl_tids_magnets(self, tids: List[str], forum_id: str, progress_callback: Optional[Callable] = None) -> List[Dict[str, Any]]:
        """爬取TID列表的磁力链接"""
        results = []
        total_tids = len(tids)
        
        # 使用线程池并发爬取
        with ThreadPoolExecutor(max_workers=self.worker_count) as executor:
            futures = []
            
            for tid in tids:
                # 检查停止标志
                if self.stop_flag():
                    logger.info("检测到停止信号，终止爬取任务")
                    break
                    
                future = executor.submit(self._crawl_single_tid_magnets, tid, forum_id)
                futures.append((tid, future))
            
            for idx, (tid, future) in enumerate(futures):
                # 检查停止标志
                if self.stop_flag():
                    logger.info("检测到停止信号，终止处理剩余任务")
                    # 取消未完成的任务
                    for remaining_tid, remaining_future in futures[idx:]:
                        try:
                            remaining_future.cancel()
                        except Exception:
                            pass
                    # 强制关闭线程池
                    executor.shutdown(wait=False)
                    break
                    
                try:
                    # 随机延迟
                    delay = self.min_wait_time + random.randint(0, self.random_delay)
                    
                    # 分段检查停止标志
                    for _ in range(delay):
                        if self.stop_flag():
                            logger.info("检测到停止信号，终止等待")
                            break
                        time.sleep(1)
                    
                    if self.stop_flag():
                        break
                    
                    result = future.result(timeout=120)
                    results.append(result)
                    
                    # 更新统计
                    with self._lock:
                        self.stats['total_processed'] += 1
                        if result.get('success'):
                            self.stats['success_count'] += 1
                        else:
                            self.stats['error_count'] += 1
                    
                    # 更新进度
                    if progress_callback:
                        progress = 50 + int((idx + 1) / total_tids * 50)
                        progress_callback(progress, f"处理TID {tid} ({idx + 1}/{total_tids})")
                    
                    logger.debug(f"完成TID {tid} ({idx + 1}/{total_tids})")
                    
                except Exception as e:
                    logger.error(f"处理TID {tid} 失败: {str(e)}")
                    
                    # 添加失败结果
                    error_result = {
                        'tid': tid,
                        'url': f"{self.base_url}/forum.php?mod=viewthread&tid={tid}",
                        'forum_id': forum_id,
                        'title': '',
                        'magnets': [],
                        'success': False,
                        'message': f"处理失败: {str(e)}",
                        'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    }
                    results.append(error_result)
                    
                    with self._lock:
                        self.stats['total_processed'] += 1
                        self.stats['error_count'] += 1
        
        return results
    
    def _crawl_single_tid_magnets(self, tid: str, forum_id: str) -> Dict[str, Any]:
        """爬取单个TID的磁力链接"""
        driver = None
        try:
            driver = self._create_driver()
            
            # 首先访问首页处理年龄验证
            driver.get(self.base_url)
            self._handle_age_verification(driver)
            
            # 爬取页面磁力链接
            result = self._crawl_page_magnets(driver, tid, forum_id)
            
            return result
        
        except Exception as e:
            logger.error(f"爬取TID {tid} 磁力链接失败: {str(e)}")
            return {
                'tid': tid,
                'url': f"{self.base_url}/forum.php?mod=viewthread&tid={tid}",
                'forum_id': forum_id,
                'title': '',
                'magnets': [],
                'success': False,
                'message': f"爬取失败: {str(e)}",
                'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass