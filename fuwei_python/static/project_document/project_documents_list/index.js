// static/project_document/project_documents_list/index.js
document.addEventListener('DOMContentLoaded', () => {
    // 全局状态变量
    let currentUser = {
        id: null,
        name: '用户'
    };

    let projects = [];
    let filteredProjects = [];
    let currentPage = 1;
    let pageSize = 10;
    let totalPages = 1;
    let totalCount = 0;
    let selectedProjects = new Set();
    let searchKeyword = '';
    let filterStatus = '';
    let filterIndustry = '';
    let sortBy = 'updated_at_desc';
    let industryList = [];
    let projectToDelete = null; // 存储要删除的项目

    // DOM元素
    const elements = {
        projectsTable: document.getElementById('projects-table'),
        projectsTbody: document.getElementById('projects-tbody'),
        paginationContainer: document.getElementById('pagination-container'),
        emptyState: document.getElementById('empty-state'),
        searchInput: document.getElementById('search-input'),
        searchBtn: document.getElementById('search-btn'),
        statusFilter: document.getElementById('status-filter'),
        industryFilter: document.getElementById('industry-filter'),
        sortFilter: document.getElementById('sort-filter'),
        statsCards: document.getElementById('stats-cards'),
        selectAllCheckbox: document.getElementById('select-all-checkbox'),
        exportSelectedBtn: document.getElementById('export-selected-btn'),
        createProjectBtn: document.getElementById('create-project-btn'),
        createFirstProjectBtn: document.getElementById('create-first-project-btn'),
        refreshBtn: document.getElementById('refresh-btn'),
        deleteConfirmModal: document.getElementById('delete-confirm-modal'),
        archiveConfirmModal: document.getElementById('archive-confirm-modal'),
        batchActionModal: document.getElementById('batch-action-modal'),
        toastContainer: document.getElementById('toast-container')
    };

    // 工具函数
    const utils = {
        // 显示Toast提示 - 优化版本
        showToast: (message, type = 'info', title = '提示') => {
            const toastContainer = elements.toastContainer;
            if (!toastContainer) {
                console.error('Toast容器未找到');
                return;
            }

            // 移除旧的toast（保留最新的3个）
            const existingToasts = toastContainer.querySelectorAll('.toast');
            if (existingToasts.length >= 3) {
                existingToasts[0].remove();
            }

            const toast = document.createElement('div');
            toast.className = `toast toast-${type}`;

            const icons = {
                success: '/static/project_document/images/common/icon-success.png',
                error: '/static/project_document/images/common/icon-error.png',
                warning: '/static/project_document/images/common/icon-warning.png',
                info: '/static/project_document/images/common/icon-info.svg'
            };

            toast.innerHTML = `
                <img src="${icons[type] || icons.info}" alt="${type}" class="toast-icon">
                <div class="toast-content">
                    <div class="toast-title">${title}</div>
                    <div class="toast-message">${message}</div>
                </div>
                <button class="toast-close">&times;</button>
            `;

            toastContainer.appendChild(toast);

            // 添加动画类
            setTimeout(() => {
                toast.classList.add('show');
            }, 10);

            // 添加关闭事件
            const closeBtn = toast.querySelector('.toast-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    toast.classList.remove('show');
                    setTimeout(() => {
                        if (toast.parentNode) {
                            toast.remove();
                        }
                    }, 300);
                });
            }

            // 5秒后自动消失
            setTimeout(() => {
                if (toast.parentNode && toast.classList.contains('show')) {
                    toast.classList.remove('show');
                    setTimeout(() => {
                        if (toast.parentNode) {
                            toast.remove();
                        }
                    }, 300);
                }
            }, 5000);

            return toast;
        },

        // 显示加载状态
        showLoading: (element, message = '加载中...') => {
            if (!element) return;

            const loadingHTML = `
                <div class="loading-state" style="
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    padding: 40px;
                    color: #999;
                ">
                    <div class="loading-spinner" style="
                        width: 40px;
                        height: 40px;
                        border: 3px solid #f3f3f3;
                        border-top: 3px solid #1890ff;
                        border-radius: 50%;
                        animation: spin 1s linear infinite;
                        margin-bottom: 12px;
                    "></div>
                    <span style="font-size: 14px;">${message}</span>
                </div>
            `;

            element.innerHTML = loadingHTML;

            // 添加旋转动画
            if (!document.querySelector('#loading-animation')) {
                const style = document.createElement('style');
                style.id = 'loading-animation';
                style.textContent = `
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                `;
                document.head.appendChild(style);
            }
        },

        // 格式化日期
        formatDate: (dateString) => {
            if (!dateString) return '-';
            try {
                const date = new Date(dateString);
                const now = new Date();

                // 设置两个日期的时间部分为0，只比较日期部分
                const dateOnly = new Date(date.getFullYear(), date.getMonth(), date.getDate());
                const nowOnly = new Date(now.getFullYear(), now.getMonth(), now.getDate());

                // 计算日期差（只比较日期，忽略时间）
                const diffTime = nowOnly - dateOnly;
                const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

                // 格式化时间部分
                const timeStr = date.toLocaleTimeString('zh-CN', {
                    hour: '2-digit',
                    minute: '2-digit'
                });

                if (diffDays === 0) {
                    return `今天 ${timeStr}`;
                }
                else if (diffDays === 1) {
                    return `昨天 ${timeStr}`;
                }
                else if (diffDays === -1) {
                    return `明天 ${timeStr}`;
                }
                else if (diffDays < 7 && diffDays > 0) {
                    return `${diffDays}天前 ${timeStr}`;
                }
                else if (diffDays > -7 && diffDays < 0) {
                    return `${Math.abs(diffDays)}天后 ${timeStr}`;
                }
                // 其他情况显示完整日期
                else {
                    return date.toLocaleDateString('zh-CN', {
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit'
                    }) + ` ${timeStr}`;
                }
            } catch (error) {
                console.error('日期格式化错误:', error, dateString);
                return '-';
            }
        },

        // 格式化文件大小
        formatFileSize: (bytes) => {
            if (!bytes || bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },

        // 获取CSRF Token
        getCSRFToken: () => {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        },

        // 生成评分星星HTML
        generateRatingStars: (score) => {
            if (!score && score !== 0) return '<span style="color:#999;">-</span>';

            const safeScore = Math.min(Math.max(score, 0), 5); // 确保分数在0-5之间
            const fullStars = Math.floor(safeScore);
            const hasHalfStar = safeScore % 1 >= 0.5;
            const emptyStars = 5 - fullStars - (hasHalfStar ? 1 : 0);

            return `
                <div class="rating-display">
                    <span class="rating-score">${safeScore.toFixed(1)}</span>
                </div>
            `;
        },

        // 获取状态标签HTML
        getStatusBadge: (status) => {
            const statusConfig = {
                'draft': {
                    text: '草稿',
                    className: 'status-draft',
                    bgColor: '#e6f7ff',
                    textColor: '#1890ff',
                    borderColor: '#91d5ff'
                },
                'writing': {
                    text: '写作中',
                    className: 'status-writing',
                    bgColor: '#f6ffed',
                    textColor: '#52c41a',
                    borderColor: '#b7eb8f'
                },
                'reviewing': {
                    text: '评审中',
                    className: 'status-reviewing',
                    bgColor: '#fff7e6',
                    textColor: '#fa8c16',
                    borderColor: '#ffd591'
                },
                'completed': {
                    text: '已完成',
                    className: 'status-completed',
                    bgColor: '#f6ffed',
                    textColor: '#52c41a',
                    borderColor: '#b7eb8f'
                },
                'archived': {
                    text: '已归档',
                    className: 'status-archived',
                    bgColor: '#fafafa',
                    textColor: '#666666',
                    borderColor: '#d9d9d9'
                }
            };

            const config = statusConfig[status] || {
                text: status || '未知',
                className: 'status-unknown',
                bgColor: '#fafafa',
                textColor: '#999999',
                borderColor: '#d9d9d9'
            };

            return `
                <span class="status-badge ${config.className}" style="
                    display: inline-block;
                    padding: 2px 8px;
                    font-size: 12px;
                    border-radius: 12px;
                    background-color: ${config.bgColor};
                    color: ${config.textColor};
                    border: 1px solid ${config.borderColor};
                    font-weight: 500;
                    line-height: 18px;
                ">
                    ${config.text}
                </span>
            `;
        },

        // 解码HTML实体
        decodeHtmlEntities: (text) => {
            if (!text) return '';
            const textarea = document.createElement('textarea');
            textarea.innerHTML = text;
            return textarea.value;
        },

        // 提取纯文本（移除HTML标签）
        extractTextFromHtml: (html) => {
            if (!html) return '';
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;
            return tempDiv.textContent || tempDiv.innerText || '';
        },

        // 防止重复提交
        debounce: (func, wait) => {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        // 验证项目ID
        validateProjectId: (projectId) => {
            return projectId && !isNaN(parseInt(projectId)) && parseInt(projectId) > 0;
        }
    };

    // 返回按钮
    const go = (path) => () => window.location.href = path;
    const backLink = document.querySelector('.back-link');
    if (backLink) {
    backLink.addEventListener('click', go('/user/index'));
    }

    // API函数
    const api = {
        // 获取当前用户信息
        getCurrentUser: async () => {
            try {
                // 这里应该调用获取当前用户信息的接口
                // 暂时从localStorage获取或使用默认值
                const userId = localStorage.getItem('user_id') || 1;
                const userName = localStorage.getItem('user_name') || '用户';
                return { id: userId, name: userName };
            } catch (error) {
                console.error('获取用户信息失败:', error);
                return { id: 1, name: '用户' };
            }
        },

        // 获取行业列表
        getIndustryList: async () => {
            try {
                const response = await fetch('/project_document/industry/list', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': utils.getCSRFToken()
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.code === 200 && result.data) {
                    return result.data;
                } else {
                    utils.showToast(result.message || '获取行业列表失败', 'error', '错误');
                    return [];
                }
            } catch (error) {
                console.error('获取行业列表失败:', error);
                utils.showToast('网络错误，请稍后重试', 'error', '错误');
                return [];
            }
        },

        // 获取项目列表
        getProjects: async (params = {}) => {
            try {
                const queryParams = new URLSearchParams({
                    page: params.page || currentPage,
                    per_page: params.per_page || pageSize,
                    ...(params.status && { status: params.status }),
                    ...(params.keyword && { keyword: params.keyword }),
                    ...(params.industry && { industry: params.industry }),
                    ...(params.sort && { sort: params.sort })
                });

                const response = await fetch(`/project_document/search?${queryParams}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': utils.getCSRFToken()
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.code === 200 && result.data) {
                    return {
                        projects: result.data.projects || [],
                        pagination: result.data.pagination || {},
                        statistics: result.data.statistics || {}
                    };
                } else {
                    utils.showToast(result.message || '获取项目列表失败', 'error', '错误');
                    return { projects: [], pagination: {}, statistics: {} };
                }
            } catch (error) {
                console.error('获取项目列表失败:', error);
                utils.showToast('网络错误，请稍后重试', 'error', '错误');
                return { projects: [], pagination: {}, statistics: {} };
            }
        },

        // 删除项目
        deleteProject: async (projectId) => {
            if (!utils.validateProjectId(projectId)) {
                utils.showToast('无效的项目ID', 'error', '错误');
                return false;
            }

            try {
                const response = await fetch(`/project_document/projects/${projectId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': utils.getCSRFToken()
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.code === 200) {
                    utils.showToast('项目删除成功', 'success', '成功');
                    return true;
                } else {
                    utils.showToast(result.message || '删除失败', 'error', '错误');
                    return false;
                }
            } catch (error) {
                console.error('删除项目失败:', error);
                utils.showToast('网络错误，请稍后重试', 'error', '错误');
                return false;
            }
        },

        // 归档项目
        archiveProject: async (projectId) => {
            if (!utils.validateProjectId(projectId)) {
                utils.showToast('无效的项目ID', 'error', '错误');
                return false;
            }

            try {
                const response = await fetch(`/project_document/projects/${projectId}/archive`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': utils.getCSRFToken()
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();

                if (result.code === 200) {
                    utils.showToast('项目归档成功', 'success', '成功');
                    return true;
                } else {
                    utils.showToast(result.message || '归档失败', 'error', '错误');
                    return false;
                }
            } catch (error) {
                console.error('归档项目失败:', error);
                utils.showToast('网络错误，请稍后重试', 'error', '错误');
                return false;
            }
        }
    };

    // 初始化函数
    const init = async () => {
        try {
            // 获取当前用户信息
            currentUser = await api.getCurrentUser();

            // 获取行业列表
            industryList = await api.getIndustryList();
            populateIndustryFilter();

            // 加载项目数据
            await loadProjects();

            // 绑定事件监听器
            bindEvents();

            // 绑定模态框事件
            bindModalEvents();

            console.log('应用初始化完成');
        } catch (error) {
            console.error('应用初始化失败:', error);
            utils.showToast('应用初始化失败，请刷新页面重试', 'error', '错误');
        }
    };

    // 填充行业过滤器
    const populateIndustryFilter = () => {
        if (!elements.industryFilter) return;

        // 清空现有选项（保留第一个）
        while (elements.industryFilter.options.length > 1) {
            elements.industryFilter.remove(1);
        }

        // 添加行业选项
        industryList.forEach(industry => {
            const option = document.createElement('option');
            option.value = industry.value || industry.id || industry;
            option.textContent = industry.label || industry.name || industry;
            elements.industryFilter.appendChild(option);
        });
    };

    // 加载项目数据
    const loadProjects = async (showLoadingIndicator = true) => {
        try {
            // 显示加载状态
            if (showLoadingIndicator && elements.projectsTbody) {
                utils.showLoading(elements.projectsTbody, '加载项目中...');
            }

            const params = {
                page: currentPage,
                per_page: pageSize,
                status: filterStatus,
                keyword: searchKeyword,
                industry: filterIndustry,
                sort: sortBy
            };

            const data = await api.getProjects(params);

            projects = data.projects || [];
            filteredProjects = projects;

            if (data.pagination) {
                totalPages = data.pagination.pages || 1;
                totalCount = data.pagination.total || 0;
                currentPage = data.pagination.page || 1;
            }

            // 更新统计信息
            updateStatistics(data.statistics);

            // 渲染项目列表
            renderProjects();

            // 更新分页
            renderPagination();

            // 检查空状态
            checkEmptyState();

            // 重置选中状态
            resetSelection();
        } catch (error) {
            console.error('加载项目失败:', error);
            if (elements.projectsTbody) {
                elements.projectsTbody.innerHTML = `
                    <tr>
                        <td colspan="8" style="text-align: center; padding: 40px;">
                            <div style="color: #ff4d4f;">
                                <img src="/static/project_document/images/common/icon-error.png" alt="错误" style="width: 40px; height: 40px; margin-bottom: 12px;">
                                <div>加载失败，请刷新重试</div>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }
    };

    // 更新统计信息
    const updateStatistics = (stats) => {
        if (!elements.statsCards) return;

        const defaultStats = {
            total_count: projects.length,
            status_stats: {
                draft: projects.filter(p => p.status === 'draft').length,
                writing: projects.filter(p => p.status === 'writing').length,
                reviewing: projects.filter(p => p.status === 'reviewing').length,
                completed: projects.filter(p => p.status === 'completed').length,
                archived: projects.filter(p => p.status === 'archived').length
            }
        };

        const statistics = stats || defaultStats;

        const statCards = [
            {
                title: '总项目数',
                value: statistics.total_count || 0,
                icon: '/static/project_document/images/common/icon-folder.png',
                color: '#1890ff',
                bgColor: '#e6f7ff'
            },
            {
                title: '草稿',
                value: statistics.status_stats?.draft || 0,
                icon: '/static/project_document/images/common/icon-draft.png',
                color: '#1890ff',
                bgColor: '#e6f7ff'
            },
            {
                title: '写作中',
                value: statistics.status_stats?.writing || 0,
                icon: '/static/project_document/images/common/icon-writing.png',
                color: '#52c41a',
                bgColor: '#f6ffed'
            },
            {
                title: '评审中',
                value: statistics.status_stats?.reviewing || 0,
                icon: '/static/project_document/images/common/icon-review.png',
                color: '#fa8c16',
                bgColor: '#fff7e6'
            },
            {
                title: '已完成',
                value: statistics.status_stats?.completed || 0,
                icon: '/static/images/user-management/batch_finish_icon.svg',
                color: '#52c41a',
                bgColor: '#f6ffed'
            }
        ];

        elements.statsCards.innerHTML = statCards.map(stat => `
            <div class="stat-card" data-stat="${stat.title}">
                <div class="stat-card-header">
                    <div class="stat-icon" style="background-color: ${stat.bgColor};">
                        <img src="${stat.icon}" alt="${stat.title}">
                    </div>
                    <h4 class="stat-title">${stat.title}</h4>
                </div>
                <div class="stat-value" style="color: ${stat.color};">${stat.value}</div>
            </div>
        `).join('');
    };

    // 渲染项目列表
    const renderProjects = () => {
        if (!elements.projectsTbody) return;

        console.log('渲染项目，数量:', projects.length);

        if (projects.length === 0) {
            elements.projectsTbody.innerHTML = `
                <tr>
                    <td colspan="8" style="text-align: center; padding: 40px;">
                        <div style="color: #999; font-size: 14px;">
                            <img src="/static/project_document/images/common/empty-folder.png" alt="空文件夹" style="width: 80px; height: 80px; opacity: 0.6; margin-bottom: 16px;">
                            <div>暂无项目数据</div>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        const rows = projects.map(project => {
            const isSelected = selectedProjects.has(project.id);
            const ideaText = project.idea ? utils.extractTextFromHtml(project.idea) : '';
            const projectTitle = utils.decodeHtmlEntities(project.title || '未命名项目');

            return `
                <tr class="project-row" data-project-id="${project.id}" data-project-status="${project.status}">
                    <td class="selection-cell">
                        <input type="checkbox" class="project-checkbox"
                               data-project-id="${project.id}"
                               ${isSelected ? 'checked' : ''}
                               aria-label="选择项目：${projectTitle}">
                    </td>
                    <td class="title-cell">
                        <div class="project-title" onclick="viewProject(${project.id})" role="button" tabindex="0">
                            ${projectTitle}
                        </div>
                        ${ideaText ? `
                            <div class="project-idea" title="${ideaText}">
                                ${ideaText.substring(0, 50)}${ideaText.length > 50 ? '...' : ''}
                            </div>
                        ` : ''}
                    </td>
                    <td class="status-cell">
                        ${utils.getStatusBadge(project.status)}
                    </td>
                    <td class="industry-cell">
                        <span class="industry-text">${project.industry || '空'}</span>
                    </td>
                    <td class="rating-cell">
                        ${utils.generateRatingStars(project.total_review_score)}
                    </td>
                    <td class="date-cell created-date">
                        ${utils.formatDate(project.created_at)}
                    </td>
                    <td class="date-cell updated-date">
                        ${utils.formatDate(project.updated_at)}
                    </td>
                    <td class="actions-cell">
                        <div class="action-buttons">
                            <button style="display:none" class="action-btn view-btn" onclick="viewProject(${project.id})" title="查看项目">
                                <img src="/static/images/login/eye-icon.svg" alt="查看">
                                <span>查看</span>
                            </button>
                            <button style="display:none" class="action-btn edit-btn" onclick="editProject(${project.id})" title="编辑项目">
                                <img src="/static/project_document/images/writing-workspace/edit.png" alt="编辑">
                                <span>编辑</span>
                            </button>
                            ${project.status !== 'archived' ? `
                                <button style="display:none" class="action-btn archive-btn" onclick="archiveProjectPrompt(${project.id})" title="归档项目">
                                    <span>📝</span>
                                    <span>归档</span>
                                </button>
                            ` : ''}
                            <button class="action-btn delete-btn" onclick="deleteProjectPrompt(${project.id})" title="删除项目">
                                <img src="/static/project_document/images/common/icon-delete.png" alt="删除">
                                <span>删除</span>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        elements.projectsTbody.innerHTML = rows;

        // 重新绑定复选框事件
        bindCheckboxEvents();

        // 添加键盘事件支持
        addKeyboardSupport();
    };

    // 添加键盘支持
    const addKeyboardSupport = () => {
        const projectTitles = document.querySelectorAll('.project-title');
        projectTitles.forEach(title => {
            title.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    const projectId = title.closest('.project-row')?.dataset.projectId;
                    if (projectId) {
                        viewProject(projectId);
                    }
                }
            });
        });
    };

    // 渲染分页
    const renderPagination = () => {
        if (!elements.paginationContainer) {
            return;
        }

        if (totalPages <= 1) {
            elements.paginationContainer.innerHTML = '';
            elements.paginationContainer.style.display = 'none';
            return;
        }

        elements.paginationContainer.style.display = 'flex';

        let paginationHTML = `
            <div class="pagination-info">
                共 ${totalCount} 条记录，第 ${currentPage} / ${totalPages} 页
            </div>
            <div class="pagination-controls">
        `;

        // 上一页按钮
        paginationHTML += `
            <button class="pagination-btn prev-btn" ${currentPage === 1 ? 'disabled' : ''}>
                <span>上一页</span>
            </button>
        `;

        // 页码
        paginationHTML += '<div class="pagination-pages">';

        // 显示页码范围
        let startPage = Math.max(1, currentPage - 2);
        let endPage = Math.min(totalPages, startPage + 4);

        // 调整起始页码
        if (endPage - startPage < 4) {
            startPage = Math.max(1, endPage - 4);
        }

        // 第一页
        if (startPage > 1) {
            paginationHTML += `
                <button class="page-number" data-page="1">1</button>
                ${startPage > 2 ? '<span class="page-ellipsis">...</span>' : ''}
            `;
        }

        // 页码按钮
        for (let i = startPage; i <= endPage; i++) {
            paginationHTML += `
                <button class="page-number ${i === currentPage ? 'active' : ''}" data-page="${i}">
                    ${i}
                </button>
            `;
        }

        // 最后一页
        if (endPage < totalPages) {
            paginationHTML += `
                ${endPage < totalPages - 1 ? '<span class="page-ellipsis">...</span>' : ''}
                <button class="page-number" data-page="${totalPages}">${totalPages}</button>
            `;
        }

        paginationHTML += '</div>';

        // 下一页按钮
        paginationHTML += `
            <button class="pagination-btn next-btn" ${currentPage === totalPages ? 'disabled' : ''}>
                <span>下一页</span>
            </button>
        `;

        paginationHTML += '</div>';

        elements.paginationContainer.innerHTML = paginationHTML;

        // 绑定分页事件
        bindPaginationEvents();
    };

    // 检查空状态
    const checkEmptyState = () => {
        if (!elements.emptyState || !elements.projectsTable) return;

        if (projects.length === 0) {
            elements.projectsTable.style.display = 'none';
            elements.paginationContainer.style.display = 'none';
            elements.emptyState.style.display = 'flex';
        } else {
            elements.projectsTable.style.display = 'table';
            elements.emptyState.style.display = 'none';
        }
    };

    // 绑定事件
    const bindEvents = () => {
        // 搜索按钮
        if (elements.searchBtn) {
            elements.searchBtn.addEventListener('click', performSearch);
        }

        // 搜索输入框回车键和输入防抖
        if (elements.searchInput) {
            // 回车搜索
            elements.searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    performSearch();
                }
            });

            // 输入防抖（500ms）
            const debouncedSearch = utils.debounce(performSearch, 500);
            elements.searchInput.addEventListener('input', debouncedSearch);
        }

        // 过滤器变化
        if (elements.statusFilter) {
            elements.statusFilter.addEventListener('change', (e) => {
                filterStatus = e.target.value;
                currentPage = 1;
                loadProjects();
            });
        }

        if (elements.industryFilter) {
            elements.industryFilter.addEventListener('change', (e) => {
                filterIndustry = e.target.value;
                currentPage = 1;
                loadProjects();
            });
        }

        if (elements.sortFilter) {
            elements.sortFilter.addEventListener('change', (e) => {
                sortBy = e.target.value;
                currentPage = 1;
                loadProjects();
            });
        }

        // 全选复选框
        if (elements.selectAllCheckbox) {
            elements.selectAllCheckbox.addEventListener('change', (e) => {
                const isChecked = e.target.checked;
                const checkboxes = document.querySelectorAll('.project-checkbox');

                checkboxes.forEach(checkbox => {
                    checkbox.checked = isChecked;
                    const projectId = parseInt(checkbox.dataset.projectId);

                    if (isChecked) {
                        selectedProjects.add(projectId);
                    } else {
                        selectedProjects.delete(projectId);
                    }
                });

                updateSelectedCount();
            });
        }

        // 导出选中按钮
        if (elements.exportSelectedBtn) {
            elements.exportSelectedBtn.addEventListener('click', exportSelectedProjects);
        }

        // 创建项目按钮
        if (elements.createProjectBtn) {
            elements.createProjectBtn.addEventListener('click', createNewProject);
        }

        if (elements.createFirstProjectBtn) {
            elements.createFirstProjectBtn.addEventListener('click', createNewProject);
        }

        // 刷新按钮
        if (elements.refreshBtn) {
            elements.refreshBtn.addEventListener('click', () => {
                currentPage = 1;
                loadProjects();
                flash('列表已刷新');
            });
        }

        // 批量操作弹窗
        if (elements.batchActionModal) {
            const batchItems = elements.batchActionModal.querySelectorAll('.batch-action-item');
            batchItems.forEach(item => {
                item.addEventListener('click', () => {
                    const action = item.dataset.action;
                    handleBatchAction(action);
                });
            });
        }
    };

    // 绑定复选框事件
    const bindCheckboxEvents = () => {
        const checkboxes = document.querySelectorAll('.project-checkbox');

        checkboxes.forEach(checkbox => {
            // 移除旧的事件监听器（避免重复绑定）
            const newCheckbox = checkbox.cloneNode(true);
            checkbox.parentNode.replaceChild(newCheckbox, checkbox);

            newCheckbox.addEventListener('change', (e) => {
                const projectId = parseInt(e.target.dataset.projectId);

                if (e.target.checked) {
                    selectedProjects.add(projectId);
                } else {
                    selectedProjects.delete(projectId);
                    if (elements.selectAllCheckbox) {
                        elements.selectAllCheckbox.checked = false;
                    }
                }

                updateSelectedCount();
            });
        });
    };

    // 绑定分页事件
    const bindPaginationEvents = () => {
        // 上一页按钮
        const prevBtn = elements.paginationContainer?.querySelector('.prev-btn');
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (currentPage > 1) {
                    currentPage--;
                    loadProjects();
                }
            });
        }

        // 下一页按钮
        const nextBtn = elements.paginationContainer?.querySelector('.next-btn');
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (currentPage < totalPages) {
                    currentPage++;
                    loadProjects();
                }
            });
        }

        // 页码按钮
        const pageNumbers = elements.paginationContainer?.querySelectorAll('.page-number');
        pageNumbers?.forEach(btn => {
            btn.addEventListener('click', () => {
                const page = parseInt(btn.dataset.page);
                if (page && page !== currentPage) {
                    currentPage = page;
                    loadProjects();
                }
            });
        });
    };

    // 绑定模态框事件
    const bindModalEvents = () => {
        // 删除确认模态框
        const deleteModal = elements.deleteConfirmModal;
        if (deleteModal) {
            // 关闭按钮
            const closeBtn = deleteModal.querySelector('#close-delete-modal');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    hideModal(deleteModal);
                });
            }

            // 取消按钮
            const cancelBtn = deleteModal.querySelector('#cancel-delete-btn');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    hideModal(deleteModal);
                });
            }

            // 确认删除按钮
            const confirmBtn = deleteModal.querySelector('#confirm-delete-btn');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', handleDeleteConfirm);
            }

            // 点击遮罩层关闭
            deleteModal.addEventListener('click', (e) => {
                if (e.target === deleteModal) {
                    hideModal(deleteModal);
                }
            });
        }

        // 归档确认模态框
        const archiveModal = elements.archiveConfirmModal;
        if (archiveModal) {
            // 关闭按钮
            const closeBtn = archiveModal.querySelector('#close-archive-modal');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    hideModal(archiveModal);
                });
            }

            // 取消按钮
            const cancelBtn = archiveModal.querySelector('#cancel-archive-btn');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    hideModal(archiveModal);
                });
            }

            // 确认归档按钮
            const confirmBtn = archiveModal.querySelector('#confirm-archive-btn');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', handleArchiveConfirm);
            }

            // 点击遮罩层关闭
            archiveModal.addEventListener('click', (e) => {
                if (e.target === archiveModal) {
                    hideModal(archiveModal);
                }
            });
        }

        // 批量操作模态框
        const batchModal = elements.batchActionModal;
        if (batchModal) {
            // 关闭按钮
            const closeBtn = batchModal.querySelector('#close-batch-modal');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    hideModal(batchModal);
                });
            }

            // 点击遮罩层关闭
            batchModal.addEventListener('click', (e) => {
                if (e.target === batchModal) {
                    hideModal(batchModal);
                }
            });
        }
    };

    // 显示模态框
    const showModal = (modal) => {
        if (!modal) return;

        modal.style.display = 'flex';
        // 触发重排以启用动画
        modal.offsetHeight;
        modal.classList.add('show');

        // 添加ESC键关闭支持
        const handleEscKey = (e) => {
            if (e.key === 'Escape') {
                hideModal(modal);
                document.removeEventListener('keydown', handleEscKey);
            }
        };
        document.addEventListener('keydown', handleEscKey);
    };

    // 隐藏模态框
    const hideModal = (modal) => {
        if (!modal) return;

        modal.classList.remove('show');
        modal.classList.add('modal-hide');

        setTimeout(() => {
            modal.style.display = 'none';
            modal.classList.remove('modal-hide');
        }, 300);
    };

    // 更新选中项目计数
    const updateSelectedCount = () => {
        if (!elements.exportSelectedBtn) return;

        if (selectedProjects.size > 0) {
            elements.exportSelectedBtn.style.display = 'none';
            elements.exportSelectedBtn.innerHTML = `
                <img src="/static/project_document/images/common/icon-export.svg" alt="导出">
                <span>导出选中(${selectedProjects.size})</span>
            `;

            if (elements.selectAllCheckbox) {
                elements.selectAllCheckbox.checked = selectedProjects.size === projects.length;
                elements.selectAllCheckbox.indeterminate = selectedProjects.size > 0 && selectedProjects.size < projects.length;
            }
        } else {
            elements.exportSelectedBtn.style.display = 'none';
            if (elements.selectAllCheckbox) {
                elements.selectAllCheckbox.checked = false;
                elements.selectAllCheckbox.indeterminate = false;
            }
        }
    };

    // 重置选中状态
    const resetSelection = () => {
        selectedProjects.clear();
        updateSelectedCount();
    };

    // 执行搜索
    const performSearch = () => {
        searchKeyword = elements.searchInput.value.trim();
        currentPage = 1;
        loadProjects();
    };

    // 查看项目
    window.viewProject = (projectId) => {
        if (!utils.validateProjectId(projectId)) {
            utils.showToast('无效的项目ID', 'error', '错误');
            return;
        }
        window.location.href = `/project_document/writing-workspace/${projectId}`;
    };

    // 编辑项目
    window.editProject = (projectId) => {
        if (!utils.validateProjectId(projectId)) {
            utils.showToast('无效的项目ID', 'error', '错误');
            return;
        }
        window.location.href = `/project_document/outline-draft?edit=${projectId}`;
    };

    // 删除项目提示
    window.deleteProjectPrompt = (projectId) => {
        if (!utils.validateProjectId(projectId)) {
            utils.showToast('无效的项目ID', 'error', '错误');
            return;
        }

        const project = projects.find(p => p.id === projectId);
        if (!project) {
            utils.showToast('未找到项目', 'error', '错误');
            return;
        }

        projectToDelete = project;

        const modal = elements.deleteConfirmModal;
        const message = modal.querySelector('#delete-message');
        const confirmBtn = modal.querySelector('#confirm-delete-btn');

        if (message && confirmBtn) {
            const projectTitle = utils.decodeHtmlEntities(project.title || '未命名项目');
            message.textContent = `确定要删除项目"${projectTitle}"吗？此操作不可恢复，所有相关内容将被永久删除。`;
            confirmBtn.dataset.projectId = projectId;

            // 禁用按钮，防止重复点击
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '确认删除';

            showModal(modal);
        }
    };

    // 处理删除确认
    const handleDeleteConfirm = async () => {
        const confirmBtn = elements.deleteConfirmModal.querySelector('#confirm-delete-btn');
        if (!confirmBtn || !projectToDelete) return;

        const projectId = projectToDelete.id;
        const projectTitle = utils.decodeHtmlEntities(projectToDelete.title || '未命名项目');

        // 禁用按钮，显示加载状态
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = `
            <span class="btn-loading"></span>
            删除中...
        `;

        try {
            const success = await api.deleteProject(projectId);

            if (success) {
                // 隐藏模态框
                hideModal(elements.deleteConfirmModal);

                // 重新加载项目列表
                await loadProjects();

                // 重置删除状态
                projectToDelete = null;
            } else {
                // 重置按钮状态
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '确认删除';
            }
        } catch (error) {
            console.error('删除过程出错:', error);
            // 重置按钮状态
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '确认删除';
        }
    };

    // 归档项目提示
    window.archiveProjectPrompt = (projectId) => {
        if (!utils.validateProjectId(projectId)) {
            utils.showToast('无效的项目ID', 'error', '错误');
            return;
        }

        const project = projects.find(p => p.id === projectId);
        if (!project) {
            utils.showToast('未找到项目', 'error', '错误');
            return;
        }

        const modal = elements.archiveConfirmModal;
        const message = modal.querySelector('#archive-message');
        const confirmBtn = modal.querySelector('#confirm-archive-btn');

        if (message && confirmBtn) {
            const projectTitle = utils.decodeHtmlEntities(project.title || '未命名项目');
            message.textContent = `确定要将项目"${projectTitle}"归档吗？归档后项目将不再显示在默认列表中，但仍可从归档列表中查看。`;
            confirmBtn.dataset.projectId = projectId;
            showModal(modal);
        }
    };

    // 处理归档确认
    const handleArchiveConfirm = async () => {
        const confirmBtn = elements.archiveConfirmModal.querySelector('#confirm-archive-btn');
        if (!confirmBtn) return;

        const projectId = confirmBtn.dataset.projectId;

        // 禁用按钮，显示加载状态
        confirmBtn.disabled = true;
        confirmBtn.innerHTML = `
            <span class="btn-loading"></span>
            归档中...
        `;

        try {
            const success = await api.archiveProject(projectId);

            if (success) {
                // 隐藏模态框
                hideModal(elements.archiveConfirmModal);

                // 重新加载项目列表
                await loadProjects();
            } else {
                // 重置按钮状态
                confirmBtn.disabled = false;
                confirmBtn.innerHTML = '确认归档';
            }
        } catch (error) {
            console.error('归档过程出错:', error);
            // 重置按钮状态
            confirmBtn.disabled = false;
            confirmBtn.innerHTML = '确认归档';
        }
    };

    // 导出选中项目
    const exportSelectedProjects = () => {
        if (selectedProjects.size === 0) {
            utils.showToast('请先选择要导出的项目', 'warning', '提示');
            return;
        }

        utils.showToast(`正在准备导出 ${selectedProjects.size} 个项目...`, 'info', '导出中');

        // 这里实现导出逻辑
        // 实际项目中可能需要调用导出API
        setTimeout(() => {
            utils.showToast('导出成功！已开始下载导出文件', 'success', '成功');
        }, 2000);
    };

    // 批量操作
    const handleBatchAction = (action) => {
        if (selectedProjects.size === 0) {
            utils.showToast('请先选择要操作的项目', 'warning', '提示');
            hideModal(elements.batchActionModal);
            return;
        }

        switch (action) {
            case 'archive':
                // 批量归档
                handleBatchArchive();
                break;
            case 'delete':
                // 批量删除
                handleBatchDelete();
                break;
            case 'export':
                // 批量导出
                exportSelectedProjects();
                break;
        }

        hideModal(elements.batchActionModal);
    };

    // 批量删除
    const handleBatchDelete = async () => {
        const confirmDelete = confirm(`确定要删除选中的 ${selectedProjects.size} 个项目吗？此操作不可恢复。`);

        if (!confirmDelete) return;

        const projectIds = Array.from(selectedProjects);
        let successCount = 0;
        let failCount = 0;

        // 显示进度提示
        utils.showToast(`正在删除 ${projectIds.length} 个项目...`, 'info', '批量删除');

        for (const projectId of projectIds) {
            try {
                const success = await api.deleteProject(projectId);
                if (success) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
                console.error(`删除项目 ${projectId} 失败:`, error);
            }
        }

        // 重新加载列表
        await loadProjects();

        // 显示结果
        if (failCount === 0) {
            utils.showToast(`成功删除 ${successCount} 个项目`, 'success', '批量删除完成');
        } else {
            utils.showToast(`删除完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning', '批量删除结果');
        }
    };

    // 批量归档
    const handleBatchArchive = async () => {
        const confirmArchive = confirm(`确定要归档选中的 ${selectedProjects.size} 个项目吗？`);

        if (!confirmArchive) return;

        const projectIds = Array.from(selectedProjects);
        let successCount = 0;
        let failCount = 0;

        // 显示进度提示
        utils.showToast(`正在归档 ${projectIds.length} 个项目...`, 'info', '批量归档');

        for (const projectId of projectIds) {
            try {
                const success = await api.archiveProject(projectId);
                if (success) {
                    successCount++;
                } else {
                    failCount++;
                }
            } catch (error) {
                failCount++;
                console.error(`归档项目 ${projectId} 失败:`, error);
            }
        }

        // 重新加载列表
        await loadProjects();

        // 显示结果
        if (failCount === 0) {
            utils.showToast(`成功归档 ${successCount} 个项目`, 'success', '批量归档完成');
        } else {
            utils.showToast(`归档完成：成功 ${successCount} 个，失败 ${failCount} 个`, 'warning', '批量归档结果');
        }
    };

    // 创建新项目
    const createNewProject = () => {
        window.location.href = '/project_document/outline-draft';
    };

    // 初始化应用
    init();
});