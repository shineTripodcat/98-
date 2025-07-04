// Web爬虫管理系统前端JavaScript
class CrawlerApp {
    constructor() {
        this.socket = io();
        this.currentTaskId = null;
        this.config = {};
        this.tasks = new Map(); // 存储所有任务
        this.taskPollingInterval = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupSocketEvents();
        this.loadInitialData();
        this.startAutoRefresh();
    }

    setupEventListeners() {
        // 导航切换
        document.querySelectorAll('[data-tab]').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                this.switchTab(link.dataset.tab);
            });
        });

        // 配置表单事件
        document.getElementById('config-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.saveConfig();
        });
        
        // 115网盘配置表单事件
        document.getElementById('pan115-config-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this.savePan115Config();
        });
    }

    setupSocketEvents() {
        this.socket.on('connect', () => {
            console.log('WebSocket连接成功');
        });

        this.socket.on('disconnect', () => {
            console.log('WebSocket连接断开');
        });

        this.socket.on('task_update', (data) => {
            this.updateTaskStatus(data);
        });

        this.socket.on('log_update', (data) => {
            this.appendLog(data.message);
        });
    }

    switchTab(tabName) {
        // 隐藏所有标签页
        document.querySelectorAll('.tab-content').forEach(tab => {
            tab.style.display = 'none';
        });

        // 移除所有导航链接的active类
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });

        // 显示目标标签页
        const targetTab = document.getElementById(`${tabName}-tab`);
        if (targetTab) {
            targetTab.style.display = 'block';
        }

        // 添加active类到当前导航链接
        const activeLink = document.querySelector(`[data-tab="${tabName}"]`);
        if (activeLink) {
            activeLink.classList.add('active');
        }

        // 更新页面标题
        const titles = {
            'dashboard': '仪表板',
            'config': '配置管理',
            'pan115': '网盘配置',
            'results': '结果管理',
            'logs': '日志查看',
            'system': '系统信息'
        };
        document.getElementById('page-title').textContent = titles[tabName] || '未知页面';

        // 加载对应数据
        this.loadTabData(tabName);
    }

    loadTabData(tabName) {
        switch (tabName) {
            case 'dashboard':
                this.loadDashboard();
                break;
            case 'config':
                this.loadConfig();
                break;
            case 'pan115':
                this.loadPan115Config();
                break;
            case 'results':
                this.loadResults();
                // 加载CSV文件列表
                loadCsvFileList();
                break;
            case 'logs':
                this.loadLogs();
                break;
            case 'system':
                this.loadSystemInfo();
                break;
        }
    }

    async loadInitialData() {
        await this.loadDashboard();
        await this.loadConfig();
        // 启动任务轮询
        this.startAllTasksPolling();
    }

    async loadDashboard() {
        try {
            await this.loadAllTasks();
            this.updateDashboardFromTasks();
        } catch (error) {
            console.error('加载仪表板数据失败:', error);
        }
    }

    async loadAllTasks() {
        try {
            const response = await fetch('/api/crawl/tasks');
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.tasks.clear();
                    result.tasks.forEach(task => {
                        this.tasks.set(task.task_id, task);
                    });
                    this.updateTasksList();
                    return result;
                }
            }
        } catch (error) {
            console.error('加载任务列表失败:', error);
        }
        return null;
    }

    updateDashboardFromTasks() {
        const stats = {
            total: this.tasks.size,
            success: 0,
            running: 0,
            failed: 0
        };

        this.tasks.forEach(task => {
            if (task.state === 'SUCCESS') {
                stats.success++;
            } else if (task.state === 'PROGRESS' || task.state === 'PENDING') {
                stats.running++;
            } else if (task.state === 'FAILURE') {
                stats.failed++;
            }
        });

        this.updateDashboardStats(stats);
    }

    updateDashboardStats(stats) {
        document.getElementById('total-tasks').textContent = stats.total;
        document.getElementById('success-tasks').textContent = stats.success;
        document.getElementById('running-tasks').textContent = stats.running;
        document.getElementById('failed-tasks').textContent = stats.failed;
    }

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.config) {
                    this.config = result.config;
                    await this.loadUserAgentOptions();
                    this.populateConfigForm();
                } else {
                    throw new Error(result.error || '获取配置失败');
                }
            } else {
                throw new Error('获取配置失败');
            }
        } catch (error) {
            console.error('加载配置失败:', error);
            this.showAlert('加载配置失败: ' + error.message, 'danger');
        }
    }

    async loadUserAgentOptions() {
        try {
            const response = await fetch('/api/user-agent-options');
            if (response.ok) {
                const data = await response.json();
                this.populateUserAgentSelect(data.options, data.display_names);
            }
        } catch (error) {
            console.error('加载用户代理选项失败:', error);
        }
    }

    populateUserAgentSelect(options, displayNames) {
        const select = document.getElementById('user-agent-select');
        select.innerHTML = '<option value="">选择用户代理...</option>';
        
        for (const [key, value] of Object.entries(options)) {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = displayNames[key] || key;
            select.appendChild(option);
        }
    }

    populateConfigForm() {
        const form = document.getElementById('config-form');
        
        // 填充基本配置
        if (this.config.basic) {
            form.querySelector('[name="base_url"]').value = this.config.basic.base_url || 'https://s9ko.avp76.net';
            form.querySelector('[name="user_agent"]').value = this.config.basic.user_agent || '';
            form.querySelector('[name="worker_count"]').value = this.config.basic.worker_count || 5;
            form.querySelector('[name="min_wait_time"]').value = this.config.basic.min_wait_time || 2;
            form.querySelector('[name="random_delay"]').value = this.config.basic.random_delay || 5;
            form.querySelector('[name="proxy"]').value = this.config.basic.proxy || '';
            form.querySelector('[name="headless"]').checked = this.config.basic.headless !== false;
            form.querySelector('[name="debug"]').checked = this.config.basic.debug || false;
        } else {
            // 设置默认值
            form.querySelector('[name="base_url"]').value = 'https://s9ko.avp76.net';
            form.querySelector('[name="worker_count"]').value = 5;
            form.querySelector('[name="min_wait_time"]').value = 2;
            form.querySelector('[name="random_delay"]').value = 5;
            form.querySelector('[name="proxy"]').value = '';
            form.querySelector('[name="headless"]').checked = true;
            form.querySelector('[name="debug"]').checked = false;
        }

        // 显示max_tid（只读）
        const maxTidDisplay = document.getElementById('max-tid-display');
        if (maxTidDisplay) {
            maxTidDisplay.value = this.config.max_tid || '0';
        }

        // 填充论坛配置
        this.populateForums();

        // 填充调度配置
        if (this.config.schedule) {
            form.querySelector('[name="schedule_enabled"]').checked = this.config.schedule.enabled || false;
            form.querySelector('[name="schedule_mode"]').value = this.config.schedule.mode || 'update_magnets';
            form.querySelector('[name="cron_expression"]').value = this.config.schedule.cron || '0 */6 * * *';
        }
    }

    populateForums() {
        const container = document.getElementById('forums-container');
        container.innerHTML = '';

        if (this.config.forums && this.config.forums.length > 0) {
            this.config.forums.forEach((forum, index) => {
                this.addForumItem(forum, index);
            });
        } else {
            this.addForumItem({}, 0);
        }
    }

    addForumItem(forum = {}, index = 0) {
        const container = document.getElementById('forums-container');
        const forumDiv = document.createElement('div');
        forumDiv.className = 'forum-item';
        forumDiv.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="mb-0">论坛 ${index + 1}</h6>
                <button type="button" class="btn btn-sm btn-outline-danger" onclick="app.removeForum(this)">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
            <div class="row">
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">论坛名称</label>
                        <input type="text" class="form-control" name="forum_name_${index}" value="${forum.name || ''}">
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="mb-3">
                        <label class="form-label">FID</label>
                        <input type="number" class="form-control" name="forum_fid_${index}" value="${forum.fid || ''}">
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="mb-3">
                        <label class="form-label">TypeID</label>
                        <input type="number" class="form-control" name="forum_typeid_${index}" value="${forum.typeid || ''}">
                    </div>
                </div>
            </div>
            <div class="row">
                <div class="col-md-3">
                    <div class="mb-3">
                        <label class="form-label">起始页</label>
                        <input type="number" class="form-control" name="forum_start_page_${index}" value="${forum.start_page || 1}" min="1">
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="mb-3">
                        <label class="form-label">结束页</label>
                        <input type="number" class="form-control" name="forum_end_page_${index}" value="${forum.end_page || 10}" min="1">
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="mb-3">
                        <label class="form-label">TID文件</label>
                        <input type="text" class="form-control" name="forum_tid_file_${index}" value="${forum.tid_file || ''}">
                    </div>
                </div>
            </div>
            <div class="form-check">
                <input class="form-check-input" type="checkbox" name="forum_enabled_${index}" ${forum.enabled ? 'checked' : ''}>
                <label class="form-check-label">启用此论坛</label>
            </div>
        `;
        container.appendChild(forumDiv);
    }

    addForum() {
        const container = document.getElementById('forums-container');
        const index = container.children.length;
        this.addForumItem({}, index);
    }

    removeForum(button) {
        const forumItem = button.closest('.forum-item');
        if (forumItem) {
            forumItem.remove();
            this.updateForumIndices();
        }
    }

    updateForumIndices() {
        const forumItems = document.querySelectorAll('.forum-item');
        forumItems.forEach((item, index) => {
            const title = item.querySelector('h6');
            if (title) {
                title.textContent = `论坛 ${index + 1}`;
            }
        });
    }

    async saveConfig() {
        try {
            const formData = new FormData(document.getElementById('config-form'));
            const config = this.formDataToConfig(formData);
            
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showAlert('配置保存成功', 'success');
                    this.config = config;
                } else {
                    throw new Error(result.error || '保存配置失败');
                }
            } else {
                throw new Error('保存配置失败');
            }
        } catch (error) {
            console.error('保存配置失败:', error);
            this.showAlert('保存配置失败: ' + error.message, 'danger');
        }
    }

    formDataToConfig(formData) {
        const config = {
            basic: {
                base_url: formData.get('base_url'),
                user_agent: formData.get('user_agent'),
                worker_count: parseInt(formData.get('worker_count')) || 5,
                min_wait_time: parseInt(formData.get('min_wait_time')) || 2,
                random_delay: parseInt(formData.get('random_delay')) || 5,
                proxy: formData.get('proxy') || '',
                headless: formData.get('headless') === 'on',
                debug: formData.get('debug') === 'on'
            },
            forums: [],
            schedule: {
                enabled: formData.get('schedule_enabled') === 'on',
                mode: formData.get('schedule_mode'),
                cron: formData.get('cron_expression')
            },
            // 保留当前的max_tid值，避免在保存配置时丢失
            max_tid: this.config.max_tid || '0'
        };

        // 收集论坛配置
        const forumItems = document.querySelectorAll('.forum-item');
        forumItems.forEach((item, index) => {
            const name = formData.get(`forum_name_${index}`);
            const fid = formData.get(`forum_fid_${index}`);
            if (name && fid) {
                config.forums.push({
                    name: name,
                    fid: parseInt(fid),
                    typeid: parseInt(formData.get(`forum_typeid_${index}`)) || 0,
                    start_page: parseInt(formData.get(`forum_start_page_${index}`)) || 1,
                    end_page: parseInt(formData.get(`forum_end_page_${index}`)) || 10,
                    tid_file: formData.get(`forum_tid_file_${index}`) || '',
                    enabled: formData.get(`forum_enabled_${index}`) === 'on'
                });
            }
        });

        return config;
    }

    async startCrawl() {
        const mode = document.getElementById('crawl-mode').value;
        await this.startCrawlWithMode(mode);
    }

    async startQuickCrawl(mode) {
        await this.startCrawlWithMode(mode);
    }

    async startCrawlWithMode(mode) {
        try {
            // 检查当前运行任务数量
            const tasksResult = await this.loadAllTasks();
            if (tasksResult && tasksResult.running_count >= tasksResult.max_concurrent) {
                this.showAlert(`已达到最大并发任务数 (${tasksResult.max_concurrent})，请等待其他任务完成`, 'warning');
                return;
            }

            // 获取当前配置
            const config = this.formDataToConfig(new FormData(document.getElementById('config-form')));
            
            const response = await fetch('/api/crawl/start', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    mode: mode,
                    config: config
                })
            });

            if (response.ok) {
                const result = await response.json();
                this.showAlert(`爬虫任务已启动 (ID: ${result.task_id})`, 'success');
                
                // 刷新任务列表
                await this.loadAllTasks();
                this.updateDashboardFromTasks();
                
                // 开始轮询所有任务状态
                this.startAllTasksPolling();
            } else {
                throw new Error('启动爬虫失败');
            }
        } catch (error) {
            console.error('启动爬虫失败:', error);
            this.showAlert('启动爬虫失败: ' + error.message, 'danger');
        }
    }

    async stopCrawl(taskId = null) {
        const targetTaskId = taskId || this.currentTaskId;
        if (!targetTaskId) {
            this.showAlert('没有指定要停止的任务', 'warning');
            return;
        }

        try {
            const response = await fetch(`/api/crawl/stop/${targetTaskId}`, {
                method: 'POST'
            });

            if (response.ok) {
                this.showAlert(`任务 ${targetTaskId} 已停止`, 'info');
                
                // 刷新任务列表
                await this.loadAllTasks();
                this.updateDashboardFromTasks();
                
                if (targetTaskId === this.currentTaskId) {
                    this.hideCrawlProgress();
                    this.currentTaskId = null;
                }
            } else {
                throw new Error('停止爬虫失败');
            }
        } catch (error) {
            console.error('停止爬虫失败:', error);
            this.showAlert('停止爬虫失败: ' + error.message, 'danger');
        }
    }

    showCrawlProgress() {
        document.getElementById('crawl-progress').style.display = 'block';
        document.getElementById('start-crawl-btn').disabled = true;
    }

    hideCrawlProgress() {
        document.getElementById('crawl-progress').style.display = 'none';
        document.getElementById('start-crawl-btn').disabled = false;
        this.updateProgress(0, '就绪');
    }

    updateProgress(percent, status) {
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const statusText = document.getElementById('status-text');

        progressBar.style.width = `${percent}%`;
        progressText.textContent = `${percent}%`;
        statusText.textContent = status;
    }

    startTaskStatusPolling() {
        if (!this.currentTaskId) return;

        const pollInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/crawl/status/${this.currentTaskId}`);
                if (response.ok) {
                    const result = await response.json();
                    if (result.success && result.task) {
                        this.updateTaskStatus(result.task);

                        if (result.task.state === 'SUCCESS' || result.task.state === 'FAILURE') {
                            clearInterval(pollInterval);
                            this.hideCrawlProgress();
                            this.currentTaskId = null;
                        }
                    }
                } else {
                    clearInterval(pollInterval);
                }
            } catch (error) {
                console.error('获取任务状态失败:', error);
                clearInterval(pollInterval);
            }
        }, 2000);
    }

    startAllTasksPolling() {
        // 清除现有的轮询
        if (this.taskPollingInterval) {
            clearInterval(this.taskPollingInterval);
        }

        this.taskPollingInterval = setInterval(async () => {
            try {
                await this.loadAllTasks();
                this.updateDashboardFromTasks();
            } catch (error) {
                console.error('轮询任务状态失败:', error);
            }
        }, 3000);
    }

    stopAllTasksPolling() {
        if (this.taskPollingInterval) {
            clearInterval(this.taskPollingInterval);
            this.taskPollingInterval = null;
        }
    }

    updateTasksList() {
        const tasksList = document.getElementById('tasks-list');
        if (!tasksList) return;

        tasksList.innerHTML = '';

        if (this.tasks.size === 0) {
            tasksList.innerHTML = '<div class="text-center text-muted py-3">暂无任务</div>';
            return;
        }

        const tasksArray = Array.from(this.tasks.values());
        tasksArray.sort((a, b) => b.created_time.localeCompare(a.created_time));

        tasksArray.forEach(task => {
            const taskCard = this.createTaskCard(task);
            tasksList.appendChild(taskCard);
        });
    }

    createTaskCard(task) {
        const card = document.createElement('div');
        card.className = 'card mb-2';
        
        const stateClass = {
            'PENDING': 'warning',
            'PROGRESS': 'primary',
            'SUCCESS': 'success',
            'FAILURE': 'danger'
        }[task.state] || 'secondary';

        const progressPercent = task.progress || 0;
        const isRunning = task.state === 'PENDING' || task.state === 'PROGRESS';

        card.innerHTML = `
            <div class="card-body p-3">
                <div class="d-flex justify-content-between align-items-start mb-2">
                    <div>
                        <h6 class="card-title mb-1">${task.task_id}</h6>
                        <span class="badge bg-${stateClass}">${task.state}</span>
                        <span class="badge bg-info ms-1">${task.mode}</span>
                    </div>
                    <div class="btn-group btn-group-sm">
                        ${isRunning ? `<button class="btn btn-outline-danger" onclick="app.stopCrawl('${task.task_id}')">停止</button>` : ''}
                    </div>
                </div>
                
                ${isRunning ? `
                    <div class="progress mb-2" style="height: 6px;">
                        <div class="progress-bar" role="progressbar" style="width: ${progressPercent}%"></div>
                    </div>
                ` : ''}
                
                <small class="text-muted">
                    ${task.status || (task.state === 'SUCCESS' ? '任务完成' : task.state === 'FAILURE' ? (task.error || '任务失败') : '等待中')}
                </small>
                
                ${task.result ? `
                    <div class="mt-2">
                        <small class="text-success">结果: ${JSON.stringify(task.result)}</small>
                    </div>
                ` : ''}
            </div>
        `;

        return card;
    }

    updateTaskStatus(status) {
        if (status.progress !== undefined) {
            this.updateProgress(status.progress, status.status || '运行中');
        }

        // 更新仪表板当前任务信息
        const currentTaskInfo = document.getElementById('current-task-info');
        if (status.state === 'PENDING' || status.state === 'PROGRESS') {
            currentTaskInfo.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <h6 class="mb-1">任务ID: ${status.task_id || this.currentTaskId}</h6>
                        <p class="mb-1">状态: <span class="badge bg-primary">${status.state}</span></p>
                        <small class="text-muted">${status.status || '运行中...'}</small>
                    </div>
                    <div class="text-end">
                        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
                    </div>
                </div>
            `;
        } else {
            currentTaskInfo.innerHTML = '<p class="text-muted">暂无运行中的任务</p>';
        }
    }

    async loadResults() {
        try {
            const response = await fetch('/api/results');
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.populateResultsTable(result.results);
                } else {
                    throw new Error(result.error || '获取结果列表失败');
                }
            } else {
                throw new Error('获取结果列表失败');
            }
        } catch (error) {
            console.error('加载结果失败:', error);
            this.showAlert('加载结果失败: ' + error.message, 'danger');
        }
    }

    populateResultsTable(results) {
        const tbody = document.getElementById('results-table-body');
        tbody.innerHTML = '';

        if (results.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">暂无结果文件</td></tr>';
            return;
        }

        results.forEach(result => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${result.filename}</td>
                <td>${this.formatFileSize(result.size)}</td>
                <td>${new Date(result.modified).toLocaleString()}</td>
                <td>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary" onclick="app.previewFile('${result.filename}')">
                            <i class="bi bi-eye"></i> 预览
                        </button>
                        <button class="btn btn-outline-success" onclick="app.downloadFile('${result.filename}')">
                            <i class="bi bi-download"></i> 下载
                        </button>
                        <button class="btn btn-outline-warning" onclick="app.transferToPan115('${result.filename}')">
                            <i class="bi bi-cloud-upload"></i> 转存115
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async previewFile(filename) {
        try {
            const response = await fetch(`/api/results/preview/${filename}`);
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showPreviewModal(result.data);
                } else {
                    throw new Error(result.error || '预览文件失败');
                }
            } else {
                throw new Error('预览文件失败');
            }
        } catch (error) {
            console.error('预览文件失败:', error);
            this.showAlert('预览文件失败: ' + error.message, 'danger');
        }
    }

    showPreviewModal(data) {
        const modal = new bootstrap.Modal(document.getElementById('previewModal'));
        const thead = document.getElementById('preview-thead');
        const tbody = document.getElementById('preview-tbody');

        // 清空表格
        thead.innerHTML = '';
        tbody.innerHTML = '';

        if (data.columns && data.columns.length > 0) {
            // 创建表头
            const headerRow = document.createElement('tr');
            data.columns.forEach(header => {
                const th = document.createElement('th');
                th.textContent = header;
                headerRow.appendChild(th);
            });
            thead.appendChild(headerRow);

            // 创建数据行
            data.rows.forEach(row => {
                const tr = document.createElement('tr');
                data.columns.forEach(column => {
                    const td = document.createElement('td');
                    td.textContent = row[column] || '';
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
        }

        modal.show();
    }

    downloadFile(filename) {
        window.open(`/api/results/download/${filename}`, '_blank');
    }

    async transferToPan115(filename) {
        if (!filename.endsWith('.csv')) {
            this.showAlert('只能转存CSV文件到115网盘', 'warning');
            return;
        }

        const confirmed = confirm(`确定要将文件 "${filename}" 转存到115网盘吗？\n\n这将提取CSV文件中的所有磁力链接，去重后分批推送到115网盘。`);
        if (!confirmed) {
            return;
        }

        try {
            const response = await fetch('/api/pan115/manual-transfer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ csv_filename: filename })
            });

            const result = await response.json();

            if (result.success) {
                this.showAlert(`转存任务已启动！处理了 ${result.total_count || 0} 条记录，成功转存 ${result.success_count || 0} 个文件`, 'success');
            } else {
                throw new Error(result.error || '转存失败');
            }
        } catch (error) {
            console.error('转存到115网盘失败:', error);
            this.showAlert('转存到115网盘失败: ' + error.message, 'danger');
        }
    }

    async loadCsvFiles() {
        try {
            const response = await fetch('/api/results/csv-files');
            const result = await response.json();
            
            const selector = document.getElementById('csv-file-selector');
            selector.innerHTML = '';
            
            if (result.success && result.files.length > 0) {
                result.files.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file.filename;
                    option.textContent = `${file.filename} (${this.formatFileSize(file.size)}) - ${new Date(file.modified).toLocaleString()}`;
                    selector.appendChild(option);
                });
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.disabled = true;
                option.textContent = '暂无CSV文件';
                selector.appendChild(option);
            }
        } catch (error) {
            console.error('加载CSV文件列表失败:', error);
            this.showAlert('加载CSV文件列表失败: ' + error.message, 'danger');
        }
    }



    async loadLogs() {
        const lines = document.getElementById('log-lines').value;
        try {
            const response = await fetch(`/api/logs?lines=${lines}`);
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.displayLogs(result.logs);
                } else {
                    throw new Error(result.error || '获取日志失败');
                }
            } else {
                throw new Error('获取日志失败');
            }
        } catch (error) {
            console.error('加载日志失败:', error);
            this.showAlert('加载日志失败: ' + error.message, 'danger');
        }
    }

    displayLogs(logs) {
        const logContent = document.getElementById('log-content');
        logContent.innerHTML = logs.map(log => `<div>${this.escapeHtml(log)}</div>`).join('');
        logContent.scrollTop = logContent.scrollHeight;
    }

    appendLog(message) {
        const logContent = document.getElementById('log-content');
        const logDiv = document.createElement('div');
        logDiv.textContent = message;
        logContent.appendChild(logDiv);
        logContent.scrollTop = logContent.scrollHeight;
    }

    async loadSystemInfo() {
        try {
            const response = await fetch('/api/system/info');
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.displaySystemInfo(result.info);
                } else {
                    throw new Error(result.error || '获取系统信息失败');
                }
            } else {
                throw new Error('获取系统信息失败');
            }
        } catch (error) {
            console.error('加载系统信息失败:', error);
            this.showAlert('加载系统信息失败: ' + error.message, 'danger');
        }
    }

    displaySystemInfo(info) {
        const systemInfo = document.getElementById('system-info');
        const resourceInfo = document.getElementById('resource-info');

        systemInfo.innerHTML = `
            <div class="row">
                <div class="col-6"><strong>操作系统:</strong></div>
                <div class="col-6">${info.system || 'N/A'}</div>
            </div>
            <div class="row">
                <div class="col-6"><strong>Python版本:</strong></div>
                <div class="col-6">${info.python_version || 'N/A'}</div>
            </div>
            <div class="row">
                <div class="col-6"><strong>CPU核心数:</strong></div>
                <div class="col-6">${info.cpu_count || 'N/A'}</div>
            </div>
            <div class="row">
                <div class="col-6"><strong>总内存:</strong></div>
                <div class="col-6">${this.formatFileSize(info.total_memory || 0)}</div>
            </div>
        `;

        resourceInfo.innerHTML = `
            <div class="mb-3">
                <div class="d-flex justify-content-between">
                    <span>CPU使用率</span>
                    <span>${(info.cpu_percent || 0).toFixed(1)}%</span>
                </div>
                <div class="progress">
                    <div class="progress-bar" style="width: ${info.cpu_percent || 0}%"></div>
                </div>
            </div>
            <div class="mb-3">
                <div class="d-flex justify-content-between">
                    <span>内存使用率</span>
                    <span>${(info.memory_percent || 0).toFixed(1)}%</span>
                </div>
                <div class="progress">
                    <div class="progress-bar bg-success" style="width: ${info.memory_percent || 0}%"></div>
                </div>
            </div>
            <div class="mb-3">
                <div class="d-flex justify-content-between">
                    <span>磁盘使用率</span>
                    <span>${(info.disk_percent || 0).toFixed(1)}%</span>
                </div>
                <div class="progress">
                    <div class="progress-bar bg-warning" style="width: ${info.disk_percent || 0}%"></div>
                </div>
            </div>
        `;
    }

    startAutoRefresh() {
        // 每30秒自动刷新仪表板
        setInterval(() => {
            if (document.querySelector('[data-tab="dashboard"]').classList.contains('active')) {
                this.loadDashboard();
            }
        }, 30000);
    }

    refreshData() {
        const activeTab = document.querySelector('.nav-link.active');
        if (activeTab) {
            this.loadTabData(activeTab.dataset.tab);
        }
    }

    showAlert(message, type = 'info') {
        // 创建警告框
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
        alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        document.body.appendChild(alertDiv);

        // 3秒后自动移除
        setTimeout(() => {
            if (alertDiv.parentNode) {
                alertDiv.parentNode.removeChild(alertDiv);
            }
        }, 3000);
    }

    async testProxy() {
        const proxyInput = document.getElementById('proxy-input');
        const testBtn = document.getElementById('test-proxy-btn');
        const resultDiv = document.getElementById('proxy-test-result');
        
        const proxyUrl = proxyInput.value.trim();
        if (!proxyUrl) {
            this.showAlert('请先输入代理地址', 'warning');
            return;
        }
        
        // 显示测试中状态
        testBtn.disabled = true;
        testBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> 测试中...';
        resultDiv.style.display = 'none';
        
        try {
            const response = await fetch('/api/proxy/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ proxy: proxyUrl })
            });
            
            const result = await response.json();
            
            if (result.success) {
                resultDiv.className = 'mt-2 alert alert-success py-2';
                resultDiv.innerHTML = `<i class="bi bi-check-circle"></i> 代理连通性测试成功！响应时间: ${result.response_time}ms`;
            } else {
                resultDiv.className = 'mt-2 alert alert-danger py-2';
                resultDiv.innerHTML = `<i class="bi bi-x-circle"></i> 代理连通性测试失败: ${result.error}`;
            }
            
            resultDiv.style.display = 'block';
            
        } catch (error) {
            resultDiv.className = 'mt-2 alert alert-danger py-2';
            resultDiv.innerHTML = `<i class="bi bi-x-circle"></i> 测试请求失败: ${error.message}`;
            resultDiv.style.display = 'block';
        } finally {
            // 恢复按钮状态
            testBtn.disabled = false;
            testBtn.innerHTML = '<i class="bi bi-wifi"></i> 测试连通性';
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // 115网盘配置相关方法
    async loadPan115Config() {
        try {
            const response = await fetch('/api/pan115/config');
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.config) {
                    this.populatePan115ConfigForm(result.config);
                    // 显示缓存的登录状态（如果有）
                    this.displayCachedLoginStatus();
                    // 显示缓存的文件夹列表（如果有）
                    this.displayCachedFoldersList();
                } else {
                    throw new Error(result.error || '获取115网盘配置失败');
                }
            } else {
                throw new Error('获取115网盘配置失败');
            }
        } catch (error) {
            console.error('加载115网盘配置失败:', error);
            this.showAlert('加载115网盘配置失败: ' + error.message, 'danger');
        }
    }

    populatePan115ConfigForm(config) {
        const form = document.getElementById('pan115-config-form');
        
        // 填充表单字段
        Object.keys(config).forEach(key => {
            const element = form.querySelector(`[name="${key}"]`);
            if (element) {
                if (element.type === 'checkbox') {
                    element.checked = config[key];
                } else {
                    element.value = config[key] || '';
                }
            }
        });
    }

    async savePan115Config() {
        try {
            const form = document.getElementById('pan115-config-form');
            const formData = new FormData(form);
            const config = {};
            
            // 收集表单数据
            for (let [key, value] of formData.entries()) {
                const element = form.querySelector(`[name="${key}"]`);
                if (element && element.type === 'checkbox') {
                    config[key] = element.checked;
                } else if (element && element.type === 'number') {
                    config[key] = parseInt(value) || 0;
                } else {
                    config[key] = value;
                }
            }
            
            // 处理未选中的复选框
            form.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                if (!formData.has(checkbox.name)) {
                    config[checkbox.name] = false;
                }
            });
            
            const response = await fetch('/api/pan115/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });
            
            const result = await response.json();
            if (result.success) {
                this.showAlert('115网盘配置保存成功', 'success');
            } else {
                throw new Error(result.error || '保存失败');
            }
        } catch (error) {
            console.error('保存115网盘配置失败:', error);
            this.showAlert('保存115网盘配置失败: ' + error.message, 'danger');
        }
    }

    displayCachedLoginStatus() {
        // 显示缓存的登录状态
        const cachedStatus = localStorage.getItem('pan115_login_status');
        const statusDiv = document.getElementById('pan115-login-status');
        
        if (cachedStatus) {
            const statusData = JSON.parse(cachedStatus);
            const cacheTime = statusData.timestamp;
            const currentTime = Date.now();
            
            // 如果缓存时间超过5分钟，显示过期提示
            if (currentTime - cacheTime > 5 * 60 * 1000) {
                statusDiv.innerHTML = `
                    <div class="alert alert-warning mb-0">
                        <i class="bi bi-clock"></i> 登录状态已过期，请点击"检查登录"刷新
                    </div>
                `;
            } else {
                // 显示缓存的状态
                const status = statusData.logged_in ? 'success' : 'danger';
                const icon = statusData.logged_in ? 'check-circle' : 'x-circle';
                statusDiv.innerHTML = `
                    <div class="alert alert-${status} mb-0">
                        <i class="bi bi-${icon}"></i> ${statusData.message}
                        <small class="d-block mt-1 text-muted">缓存状态，点击"检查登录"刷新</small>
                    </div>
                `;
            }
        } else {
            statusDiv.innerHTML = '<p class="text-muted">请先配置Cookie文件，然后点击"检查登录"</p>';
        }
    }
    
    displayCachedFoldersList() {
        // 显示缓存的文件夹列表
        const cachedFolders = localStorage.getItem('pan115_folders_cache');
        const foldersDiv = document.getElementById('pan115-folders-list');
        
        if (cachedFolders) {
            const cacheData = JSON.parse(cachedFolders);
            const currentTime = Date.now();
            
            // 如果缓存时间在10分钟内，显示缓存数据
            if (currentTime - cacheData.timestamp < 10 * 60 * 1000) {
                this.displayFoldersList(cacheData.folders, false);
            } else {
                foldersDiv.innerHTML = `
                    <div class="alert alert-warning mb-0">
                        <i class="bi bi-clock"></i> 文件夹列表已过期，请点击"获取文件夹"刷新
                    </div>
                `;
            }
        } else {
            foldersDiv.innerHTML = '<p class="text-muted">请先检查登录状态，然后点击"获取文件夹"</p>';
        }
    }

    async checkPan115Login() {
        try {
            const statusDiv = document.getElementById('pan115-login-status');
            statusDiv.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> 检查中...';
            
            const response = await fetch('/api/pan115/check-login', {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                const status = result.logged_in ? 'success' : 'danger';
                const icon = result.logged_in ? 'check-circle' : 'x-circle';
                statusDiv.innerHTML = `
                    <div class="alert alert-${status} mb-0">
                        <i class="bi bi-${icon}"></i> ${result.message}
                    </div>
                `;
                
                // 缓存登录状态
                const statusData = {
                    logged_in: result.logged_in,
                    message: result.message,
                    timestamp: Date.now()
                };
                localStorage.setItem('pan115_login_status', JSON.stringify(statusData));
            } else {
                throw new Error(result.error || '检查失败');
            }
        } catch (error) {
            console.error('检查115网盘登录状态失败:', error);
            const errorMessage = `
                <div class="alert alert-danger mb-0">
                    <i class="bi bi-x-circle"></i> 检查失败: ${error.message}
                </div>
            `;
            document.getElementById('pan115-login-status').innerHTML = errorMessage;
            
            // 缓存错误状态
            const statusData = {
                logged_in: false,
                message: `检查失败: ${error.message}`,
                timestamp: Date.now()
            };
            localStorage.setItem('pan115_login_status', JSON.stringify(statusData));
        }
    }

    async loadPan115Folders(forceRefresh = false) {
        try {
            const foldersDiv = document.getElementById('pan115-folders-list');
            
            // 检查缓存（如果不是强制刷新）
            if (!forceRefresh) {
                const cachedFolders = localStorage.getItem('pan115_folders_cache');
                if (cachedFolders) {
                    const cacheData = JSON.parse(cachedFolders);
                    const currentTime = Date.now();
                    
                    // 如果缓存时间在10分钟内，使用缓存数据
                    if (currentTime - cacheData.timestamp < 10 * 60 * 1000) {
                        this.displayFoldersList(cacheData.folders, false);
                        return;
                    }
                }
            }
            
            foldersDiv.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> 加载中...';
            
            // 构建URL，如果需要强制刷新则添加参数
            const url = forceRefresh ? '/api/pan115/folders?force_refresh=true' : '/api/pan115/folders';
            const response = await fetch(url);
            const result = await response.json();
            
            if (result.success) {
                const folders = result.folders || [];
                
                // 缓存文件夹列表
                const cacheData = {
                    folders: folders,
                    timestamp: Date.now()
                };
                localStorage.setItem('pan115_folders_cache', JSON.stringify(cacheData));
                
                this.displayFoldersList(folders, forceRefresh);
            } else {
                throw new Error(result.error || '获取文件夹列表失败');
            }
        } catch (error) {
            console.error('加载115网盘文件夹失败:', error);
            document.getElementById('pan115-folders-list').innerHTML = `
                <div class="alert alert-danger mb-0">
                    <i class="bi bi-x-circle"></i> 加载失败: ${error.message}
                </div>
            `;
        }
    }
    
    displayFoldersList(folders, isRefreshed = false) {
        const foldersDiv = document.getElementById('pan115-folders-list');
        
        if (folders.length > 0) {
            let html = '<div class="list-group list-group-flush">';
            folders.forEach(folder => {
                html += `
                    <div class="list-group-item list-group-item-action" 
                         style="cursor: pointer; font-size: 0.875rem; padding: 0.5rem;" 
                         onclick="selectPan115Folder('${folder.id}', '${folder.name.replace(/'/g, "\\'")}')"
                         title="点击选择此文件夹">
                        <i class="bi bi-folder"></i> ${folder.name}
                        <small class="text-muted d-block">ID: ${folder.id}</small>
                    </div>
                `;
            });
            html += '</div>';
            
            // 添加缓存状态提示
            if (isRefreshed) {
                html += '<div class="mt-2"><small class="text-success"><i class="bi bi-arrow-clockwise"></i> 已刷新最新数据</small></div>';
            } else {
                html += '<div class="mt-2"><small class="text-muted"><i class="bi bi-clock"></i> 缓存数据，10分钟内有效</small></div>';
            }
            
            foldersDiv.innerHTML = html;
        } else {
            foldersDiv.innerHTML = '<p class="text-muted mb-0">未找到文件夹</p>';
        }
    }

    async showPan115QR() {
        try {
            this.showAlert('正在获取二维码...', 'info');
            
            const response = await fetch('/api/pan115/qr-login', {
                method: 'POST'
            });
            
            const result = await response.json();
            if (result.success) {
                // 创建二维码显示模态框
                const modalHtml = `
                    <div class="modal fade" id="qrModal" tabindex="-1">
                        <div class="modal-dialog modal-dialog-centered">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h5 class="modal-title">115网盘扫码登录</h5>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                                </div>
                                <div class="modal-body text-center">
                                    <img src="data:image/png;base64,${result.qr_code}" alt="二维码" class="img-fluid mb-3">
                                    <p class="text-muted">请使用115手机客户端扫描二维码登录</p>
                                    <div id="qr-status" class="mt-3">
                                        <div class="spinner-border spinner-border-sm" role="status"></div>
                                        等待扫码...
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                
                // 移除已存在的模态框
                const existingModal = document.getElementById('qrModal');
                if (existingModal) {
                    existingModal.remove();
                }
                
                // 添加新的模态框
                document.body.insertAdjacentHTML('beforeend', modalHtml);
                
                // 显示模态框
                const modal = new bootstrap.Modal(document.getElementById('qrModal'));
                modal.show();
                
                // 开始轮询登录状态
                this.pollQRLoginStatus(result.session_id, modal);
            } else {
                throw new Error(result.error || '获取二维码失败');
            }
        } catch (error) {
            console.error('显示115网盘二维码失败:', error);
            this.showAlert('显示二维码失败: ' + error.message, 'danger');
        }
    }

    async pollQRLoginStatus(sessionId, modal) {
        const statusDiv = document.getElementById('qr-status');
        let pollCount = 0;
        const maxPolls = 60; // 最多轮询60次（5分钟）
        
        const poll = async () => {
            try {
                const response = await fetch(`/api/pan115/qr-status/${sessionId}`);
                const result = await response.json();
                
                if (result.success) {
                    if (result.status === 'success') {
                        statusDiv.innerHTML = '<div class="text-success"><i class="bi bi-check-circle"></i> 登录成功！</div>';
                        setTimeout(() => {
                            modal.hide();
                            this.showAlert('115网盘登录成功！', 'success');
                            // 重新检查登录状态
                            this.checkPan115Login();
                        }, 2000);
                        return;
                    } else if (result.status === 'waiting') {
                        statusDiv.innerHTML = '<div class="spinner-border spinner-border-sm" role="status"></div> 等待扫码...';
                    } else if (result.status === 'scanned') {
                        statusDiv.innerHTML = '<div class="text-info"><i class="bi bi-phone"></i> 已扫码，请在手机上确认</div>';
                    } else if (result.status === 'expired') {
                        statusDiv.innerHTML = '<div class="text-danger"><i class="bi bi-x-circle"></i> 二维码已过期</div>';
                        return;
                    }
                }
                
                pollCount++;
                if (pollCount < maxPolls) {
                    setTimeout(poll, 5000); // 5秒后再次轮询
                } else {
                    statusDiv.innerHTML = '<div class="text-warning"><i class="bi bi-clock"></i> 登录超时</div>';
                }
            } catch (error) {
                console.error('轮询二维码状态失败:', error);
                statusDiv.innerHTML = '<div class="text-danger"><i class="bi bi-x-circle"></i> 检查状态失败</div>';
            }
        };
        
        // 开始轮询
        setTimeout(poll, 2000);
    }

    async getPan115Folders() {
        await this.loadPan115Folders(true); // 强制刷新文件夹列表
    }
}

// 全局变量和函数
let app;

// 页面加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    app = new CrawlerApp();
});

// 全局函数供HTML调用
function refreshData() {
    app.refreshData();
}

function loadConfig() {
    app.loadConfig();
}

function saveConfig() {
    app.saveConfig();
}

function addForum() {
    app.addForum();
}

function startCrawl() {
    app.startCrawl();
}

function stopCrawl() {
    app.stopCrawl();
}

function startQuickCrawl(mode) {
    app.startQuickCrawl(mode);
}

function loadResults() {
    app.loadResults();
}

function loadLogs() {
    app.loadLogs();
}

function loadSystemInfo() {
    app.loadSystemInfo();
}

function checkPan115Login() {
    app.checkPan115Login();
}

function loadPan115Folders() {
    app.loadPan115Folders();
}

function refreshPan115Folders() {
    app.loadPan115Folders(true);
}

function selectPan115Folder(folderId, folderName) {
    const input = document.querySelector('input[name="target_dir_id"]');
    if (input) {
        input.value = folderId;
        app.showAlert(`已选择文件夹: ${folderName}`, 'success');
    }
}

// 加载CSV文件列表
async function loadCsvFileList() {
    try {
        const response = await fetch('/api/results/csv-files');
        const result = await response.json();
        
        if (result.success) {
            // 填充单选列表（结果管理页面）
            const singleSelect = document.getElementById('csv-file-select');
            if (singleSelect) {
                singleSelect.innerHTML = '<option value="" disabled selected>请选择CSV文件...</option>';
                
                result.files.forEach(file => {
                    const option = document.createElement('option');
                    option.value = file.filename;
                    option.textContent = file.filename;
                    option.dataset.size = file.size;
                    option.dataset.modified = file.modified;
                    singleSelect.appendChild(option);
                 });
                 
                 // 添加选择变化事件监听器
                 singleSelect.addEventListener('change', handleCsvFileSelect);
             }
         } else {
             throw new Error(result.error || '获取CSV文件列表失败');
        }
    } catch (error) {
        console.error('加载CSV文件列表失败:', error);
        if (app && app.showAlert) {
            app.showAlert('加载CSV文件列表失败: ' + error.message, 'danger');
        }
    }
}

// 为了兼容HTML中的调用，添加别名函数
async function loadCsvFiles() {
    await loadCsvFileList();
}

// CSV文件选择处理
function handleCsvFileSelect() {
    const select = document.getElementById('csv-file-select');
    const transferBtn = document.getElementById('manual-transfer-btn');
    const cacheTransferBtn = document.getElementById('cache-transfer-btn');
    const fileInfo = document.getElementById('csv-file-info');
    const fileDetails = document.getElementById('csv-file-details');
    
    // 检查必要元素是否存在
    if (!select) return;
    
    const selectedFile = select.value;
    
    if (selectedFile) {
        // 从选项中获取文件信息
        const selectedOption = select.options[select.selectedIndex];
        const fileSize = selectedOption.dataset.size;
        const fileModified = selectedOption.dataset.modified;
        
        // 显示文件信息
        const fileSizeKB = fileSize ? (parseInt(fileSize) / 1024).toFixed(2) : '未知';
        const modifiedDate = fileModified ? new Date(fileModified).toLocaleString('zh-CN') : '未知';
        
        if (fileDetails) {
            fileDetails.innerHTML = `
                <div><strong>文件名:</strong> ${selectedFile}</div>
                <div><strong>文件大小:</strong> ${fileSizeKB} KB</div>
                <div><strong>修改时间:</strong> ${modifiedDate}</div>
            `;
        }
        if (fileInfo) {
            fileInfo.style.display = 'block';
        }
        if (transferBtn) transferBtn.disabled = false;
        if (cacheTransferBtn) cacheTransferBtn.disabled = false;
    } else {
        if (transferBtn) transferBtn.disabled = true;
        if (cacheTransferBtn) cacheTransferBtn.disabled = true;
        if (fileInfo) fileInfo.style.display = 'none';
    }
}

// 开始手动转存
async function startManualTransfer() {
    const select = document.getElementById('csv-file-select');
    const transferBtn = document.getElementById('manual-transfer-btn');
    const selectedFile = select.value;
    
    if (!selectedFile) {
        app.showAlert('请先选择CSV文件', 'warning');
        return;
    }
    
    try {
        // 禁用按钮，显示加载状态
        transferBtn.disabled = true;
        transferBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 转存中...';
        
        // 发送请求到后端
        const response = await fetch('/api/pan115/manual-transfer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ csv_filename: selectedFile })
        });
        
        const result = await response.json();
        
        if (result.success) {
            app.showAlert(`转存任务已启动！处理了 ${result.total_count || 0} 条记录，成功转存 ${result.success_count || 0} 个文件`, 'success');
            // 清空选择
            select.value = '';
            const fileInfo = document.getElementById('csv-file-info');
            if (fileInfo) fileInfo.style.display = 'none';
        } else {
            throw new Error(result.error || '转存失败');
        }
    } catch (error) {
        console.error('手动转存失败:', error);
        app.showAlert('手动转存失败: ' + error.message, 'danger');
    } finally {
        // 恢复按钮状态
        transferBtn.disabled = false;
        transferBtn.innerHTML = '<i class="bi bi-cloud-upload"></i> 直接转存';
    }
}

// 开始缓存转存
async function startCacheTransfer() {
    const select = document.getElementById('csv-file-select');
    const cacheTransferBtn = document.getElementById('cache-transfer-btn');
    const batchSizeInput = document.getElementById('batch-size-input');
    const selectedFile = select.value;
    
    if (!selectedFile) {
        app.showAlert('请先选择CSV文件', 'warning');
        return;
    }
    
    const batchSize = parseInt(batchSizeInput.value) || 50;
    if (batchSize < 1 || batchSize > 100) {
        app.showAlert('批次大小必须在1-100之间', 'warning');
        return;
    }
    
    try {
        // 禁用按钮，显示加载状态
        cacheTransferBtn.disabled = true;
        cacheTransferBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 缓存转存中...';
        
        // 发送请求到后端
        const response = await fetch('/api/pan115/transfer-with-cache', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                csv_filename: selectedFile,
                batch_size: batchSize
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            const cacheResult = result.cache_result || {};
            const processResult = result.process_result || {};
            
            let message = `缓存转存完成！\n`;
            message += `缓存阶段: 读取${cacheResult.total_read || 0}行，缓存${cacheResult.cached_count || 0}个有效链接\n`;
            message += `处理阶段: 分${processResult.total_batches || 0}批处理，成功${processResult.success_count || 0}个，失败${processResult.failed_count || 0}个`;
            
            app.showAlert(message, 'success');
            
            // 显示缓存管理区域
            showCacheManagement(result.cache_result?.cache_file);
            
            // 清空选择
            select.value = '';
            const fileInfo = document.getElementById('csv-file-info');
            if (fileInfo) fileInfo.style.display = 'none';
        } else {
            throw new Error(result.error || '缓存转存失败');
        }
    } catch (error) {
        console.error('缓存转存失败:', error);
        app.showAlert('缓存转存失败: ' + error.message, 'danger');
    } finally {
        // 恢复按钮状态
        cacheTransferBtn.disabled = false;
        cacheTransferBtn.innerHTML = '<i class="bi bi-layers"></i> 缓存转存';
    }
}

// 显示缓存管理区域
function showCacheManagement(cacheFile) {
    const cacheManagement = document.getElementById('cache-management');
    const cacheFilePath = document.getElementById('cache-file-path');
    const processCacheBtn = document.getElementById('process-cache-btn');
    
    if (cacheFile && cacheFilePath && processCacheBtn && cacheManagement) {
        cacheFilePath.value = cacheFile;
        processCacheBtn.disabled = false;
        cacheManagement.style.display = 'block';
        
        // 刷新缓存信息
        refreshCacheInfo();
    }
}

// 刷新缓存信息
async function refreshCacheInfo() {
    const cacheFilePath = document.getElementById('cache-file-path');
    const cacheInfo = document.getElementById('cache-info');
    const cacheDetails = document.getElementById('cache-details');
    
    if (!cacheFilePath || !cacheInfo || !cacheDetails) {
        return;
    }
    
    const cacheFile = cacheFilePath.value;
    if (!cacheFile) {
        return;
    }
    
    try {
        // 这里可以添加获取缓存文件信息的API调用
        // 暂时显示基本信息
        const fileName = cacheFile.split(/[\\/]/).pop();
        cacheDetails.textContent = `缓存文件: ${fileName}`;
        cacheInfo.style.display = 'block';
    } catch (error) {
        console.error('刷新缓存信息失败:', error);
    }
}

// 处理缓存文件
async function processCacheFile() {
    const cacheFilePath = document.getElementById('cache-file-path');
    const batchSizeInput = document.getElementById('batch-size-input');
    const processCacheBtn = document.getElementById('process-cache-btn');
    
    if (!cacheFilePath || !batchSizeInput || !processCacheBtn) {
        return;
    }
    
    const cacheFile = cacheFilePath.value;
    if (!cacheFile) {
        app.showAlert('未指定缓存文件', 'warning');
        return;
    }
    
    const batchSize = parseInt(batchSizeInput.value) || 50;
    if (batchSize < 1 || batchSize > 100) {
        app.showAlert('批次大小必须在1-100之间', 'warning');
        return;
    }
    
    try {
        // 禁用按钮，显示加载状态
        processCacheBtn.disabled = true;
        processCacheBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> 处理中...';
        
        // 发送请求到后端
        const response = await fetch('/api/pan115/process-cache', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                cache_file: cacheFile,
                batch_size: batchSize
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            let message = `缓存处理完成！\n`;
            message += `分${result.total_batches || 0}批处理${result.total_magnets || 0}个链接\n`;
            message += `成功${result.success_count || 0}个，失败${result.failed_count || 0}个`;
            
            app.showAlert(message, 'success');
            
            // 如果有失败详情，可以在控制台显示
            if (result.failed_details && result.failed_details.length > 0) {
                console.log('失败详情:', result.failed_details);
            }
        } else {
            throw new Error(result.error || '处理缓存失败');
        }
    } catch (error) {
        console.error('处理缓存失败:', error);
        app.showAlert('处理缓存失败: ' + error.message, 'danger');
    } finally {
        // 恢复按钮状态
        processCacheBtn.disabled = false;
        processCacheBtn.innerHTML = '<i class="bi bi-play"></i> 处理缓存';
    }
}