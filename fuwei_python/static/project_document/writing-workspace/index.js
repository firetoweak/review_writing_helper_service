// static/project_document/writing-workspace/index.js
document.addEventListener('DOMContentLoaded', () => {
    // ==================== 工具函数 ====================
    const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB 图片大小限制
    const go = (path) => () => {
        window.location.href = path;
    };

    const flash = (text) => {
        const hint = document.createElement('div');
        hint.className = 'toast-hint';
        hint.innerText = text;
        document.body.appendChild(hint);
        setTimeout(() => hint.classList.add('show'), 10);
        setTimeout(() => {
            hint.classList.remove('show');
            setTimeout(() => hint.remove(), 200);
        }, 1600);
    };

    // ==================== Markdown转换函数 ====================
    // Markdown处理器实例
    const markdownProcessor = window.MarkdownProcessor || {};

    /**
     * 处理编辑器内容中的Markdown
     * @param {string} content 编辑器内容
     * @returns {string} 处理后的HTML内容
     */
    function processEditorContent(content) {
        if (!content || typeof content !== 'string') return content || '';

        // 检查内容是否为Markdown格式
        if (markdownProcessor.isMarkdown(content)) {
            console.log('检测到Markdown格式内容，正在转换...');
            const htmlContent = markdownProcessor.markdownToHtml(content);
            flash('Markdown格式已自动转换为HTML');
            return htmlContent;
        }

        return content;
    }

    // ==================== 全局变量 ====================
    let documentId = null;
    let workspaceData = null;
    let currentSectionNodeId = null;
    let currentSectionLevel = null; // 当前节点级别：1-章节，2-小节
    let mainEditor = null;
    let aiReplyEditEditor = null;
    let isAutoSaving = false;
    let autoSaveInterval = null;
    let selectedText = '';
    let selectedRange = null;
    let isAiSuggestionPending = false;
    let chatMessages = [];
    let improvementDrafts = [];  // 改进笔记数据（未删除）
    let deletedImprovementDrafts = []; // 已删除的改进笔记数据
    let aiTopicsData = [];
    let historyData = [];
    let materialData = [];

    // 拖拽相关变量
    let isResizing = false;
    let isDraggingResizeHandle = false;
    let startX = 0;
    let startWidth = 0;

    // 选中文字工具栏相关变量
    let highlightOverlay = null;
    let editorScrollContainer = null;
    let currentHighlightNode = null;
    let ignoreSelectionOnce = false;

    // 未合入笔记弹窗相关
    let pendingUnmergedAction = null;

    // AI面板状态相关
    let isHistoryOpen = false;
    let pendingNewTopic = false;
    let uploadedFiles = [];
    let dialogUploadedFiles = []; // 对话弹窗上传的文件

    // 选中文本操作相关
    let currentOriginalText = '';      // 保存原始选中的文本
    let currentAIGeneratedText = '';   // 保存AI生成的文本
    let currentAIOperation = '';       // 当前操作类型：扩写、缩写、改写

    // 评审计时相关变量
    let reviewTimerId = null;
    let reviewSeconds = 0;
    let reviewTimerInterval = null;

    // AI对话相关变量
    let currentSessionId = null;        // 当前会话ID
    let currentMessageId = null;        // 当前消息ID
    let isStreaming = false;            // 是否正在流式接收
    let streamController = null;        // 流式请求的AbortController

    // 数据服务引用
    const DataService = window.ProjectDocumentService;

    let editingMessageData = null;  // 保存正在编辑的消息数据

    // 启发式写作相关变量
    let heuristicSessionId = null;
    let heuristicMessageId = null;
    let heuristicStreamHandler = null;
    let heuristicDialogMessages = [];
    let heuristicCurrentRound = 0;

    // 章节要点相关变量
    let currentChapterIndex = -1;      // 当前选中的章节索引
    let activeTab = 'outline';         // 当前激活的标签页：outline 或 chapter-points

    // 合并相关计时器变量
    let mergeTimerInterval = null;
    let mergeSeconds = 0;
    let isMerging = false;

    // ==================== 新增：评审按钮状态变量 ====================
    let isContentModified = false;      // 标记内容是否被修改过
    let hasReviewed = false;           // 标记当前章节是否已评审过
    let originalEditorContent = '';     // 保存评审时的编辑器内容，用于比较
    let lastReviewedNodeId = null;      // 最后评审的节点ID

    // ==================== 添加折叠状态变量 ====================
    let aiTopicsCollapsed = false; // 初始状态为展开

    // ==================== 合并按钮状态变量 ====================
    let currentMergeButtonType = 'section'; // 'section' 或 'chapter'，默认为小节

    let nodeReviewDetailContent = null

    // ==================== 评审范围状态变量 ====================
    let currentReviewScope = 'section'; // 'section' 或 'chapter'，默认显示本节评审
    let currentReviewNodeId = null;     // 当前显示的评审节点ID

    // ==================== CSS变量管理 ====================
    const CSS_VARS = {
        OUTLINE_WIDTH: '--outline-panel-width',
        OUTLINE_COLLAPSED: '--outline-panel-collapsed'
    };

    function setCssVar(variable, value) {
        document.documentElement.style.setProperty(variable, value);
    }

    function getCssVar(variable) {
        return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
    }

    // ==================== 新增：评审按钮状态管理函数 ====================
    /**
     * 更新评审按钮状态
     */
    function updateReviewButtonState() {
        const reviewSectionBtn = document.querySelector('.review-section-btn');
        if (!reviewSectionBtn) return;

        // 检查是否应该禁用评审按钮
        const shouldDisable = hasReviewed && !isContentModified && lastReviewedNodeId === currentSectionNodeId;

        if (shouldDisable) {
            disableReviewButton(reviewSectionBtn);
        } else {
            enableReviewButton(reviewSectionBtn);
        }
    }

    // 禁用评审按钮
    function disableReviewButton(buttonElement) {
        if (!buttonElement) return;

        buttonElement.classList.add('disabled');
        buttonElement.style.opacity = '0.5';
        buttonElement.style.cursor = 'not-allowed';
        buttonElement.setAttribute('title', '内容未修改或评审中，无需重新评审');
        buttonElement.disabled = true; // 添加disabled属性以完全禁用点击
    }

    // 启用评审按钮
    function enableReviewButton(buttonElement) {
        if (!buttonElement) return;

        buttonElement.classList.remove('disabled');
        buttonElement.style.opacity = '1';
        buttonElement.style.cursor = 'pointer';
        buttonElement.removeAttribute('title');
        buttonElement.disabled = false; // 移除disabled属性
    }

    /**
     * 标记内容已修改
     */
    function markContentAsModified() {
        if (!isContentModified) {
            isContentModified = true;
            console.log('内容已修改，启用评审按钮');
            updateReviewButtonState();
        }
    }

    /**
     * 标记评审已完成
     */
    function markReviewCompleted() {
        if (mainEditor) {
            // 保存当前编辑器内容作为评审基准
            if (typeof mainEditor.getHtml === 'function') {
                originalEditorContent = mainEditor.getHtml();
            } else if (typeof mainEditor.getText === 'function') {
                originalEditorContent = mainEditor.getText();
            }
        }

        hasReviewed = true;
        lastReviewedNodeId = currentSectionNodeId;
        isContentModified = false;
        console.log('评审完成，保存基准内容');
        updateReviewButtonState();
    }

    /**
     * 检查内容是否被修改
     */
    function checkContentModified() {
        if (!mainEditor || !originalEditorContent) return false;

        let currentContent = '';
        if (typeof mainEditor.getHtml === 'function') {
            currentContent = mainEditor.getHtml();
        } else if (typeof mainEditor.getText === 'function') {
            currentContent = mainEditor.getText();
        }

        // 简单比较内容是否相同
        const modified = currentContent !== originalEditorContent;
        if (isContentModified !== modified) {
            isContentModified = modified;
            console.log('内容修改状态变化:', isContentModified);
            updateReviewButtonState();
        }

        return modified;
    }

    // ==================== 初始化函数 ====================
    function initialize() {
        // 从URL获取文档ID
        documentId = getDocumentIdFromUrl();
        if (!documentId) {
            showError('无法获取文档ID');
            return;
        }

        // 初始化页面
        initPage();

        // 加载工作区数据
        loadWorkspaceData();

        // 绑定所有事件
        bindEvents();

        // 启动自动保存
        startAutoSave();

        // 启动内容修改检查定时器
        startContentCheckTimer();
    }

    /**
     * 启动内容修改检查定时器
     */
    function startContentCheckTimer() {
        // 每5秒检查一次内容是否被修改
        setInterval(() => {
            if (hasReviewed && lastReviewedNodeId === currentSectionNodeId) {
                checkContentModified();
            }
        }, 5000);
    }

    function getDocumentIdFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/writing-workspace\/(\d+)/);
        if (match && match[1]) {
            return parseInt(match[1], 10);
        }

        const params = new URLSearchParams(window.location.search);
        const idParam = params.get('document_id');
        if (idParam) {
            return parseInt(idParam, 10);
        }

        return null;
    }

    function initPage() {
        // 初始化编辑器
        initEditor();

        // 初始化步骤条
        initSteps();

        // 初始化面板状态
        initPanelStates();

        // 显示加载状态
        showLoading();
    }

    function initEditor() {
        if (window.wangEditor) {
            const { createEditor, createToolbar } = window.wangEditor;

            // 自定义粘贴处理器
            const customPasteHandler = (editor, event) => {
                event.preventDefault();
                event.stopPropagation();  // 阻止事件冒泡

                const clipboardData = event.clipboardData || window.clipboardData;
                if (!clipboardData) return;

                let text = clipboardData.getData('text/plain') || '';
                let html = clipboardData.getData('text/html') || '';

                // 如果没有HTML但有文本，检查是否为Markdown
                if (!html && text) {
                    if (markdownProcessor.isMarkdown(text)) {
                        html = markdownProcessor.markdownToHtml(text);
                        console.log('Markdown已转换为HTML');
                        flash('Markdown格式已自动转换为HTML');
                    }
                }

                // 如果有HTML，使用dangerouslyInsertHtml
                if (html) {
                    try {
                        // 只使用一种方法插入，避免重复
                        if (editor.dangerouslyInsertHtml) {
                            editor.dangerouslyInsertHtml(html);
                        } else if (editor.insertHTML) {
                            editor.insertHTML(html);
                        } else if (editor.commands && editor.commands.insertHTML) {
                            editor.commands.insertHTML(html);
                        }
                    } catch (error) {
                        console.error('插入HTML失败:', error);
                    }
                } else if (text) {
                    // 如果没有HTML，直接插入文本
                    if (editor.insertText) {
                        editor.insertText(text);
                    }
                }

                return false;  // 防止默认行为
            };

            mainEditor = createEditor({
                selector: '#editor-content',
                html: '',
                config: {
                    placeholder: '请输入正文...',
                    hoverbarKeys: {
                        text: { menuKeys: [] },
                    },
                    MENU_CONF: {
                        uploadImage: {
                            server: '/user/aiVal/upload_pic',
                            fieldName: 'file',
                            maxFileSize: MAX_IMAGE_SIZE, // 5MB
                            maxNumberOfFiles: 1,
                            // 添加自定义验证函数
                            customValidate: (file) => {
                                if (file.size > MAX_IMAGE_SIZE) {
                                    return '图片大小不能超过5MB';
                                }
                                return null;
                            },
                            // 修改错误处理
                            onError: (error, file) => {
                                console.error('图片上传失败:', error, file);
                                let message = '上传失败';

                                if (error instanceof Error) {
                                    if (error.message.includes('exceeds maximum allowed size')) {
                                        message = '图片大小不能超过5MB';
                                    } else {
                                        message = error.message;
                                    }
                                } else if (typeof error === 'string') {
                                    message = error;
                                } else if (error.size && error.size>MAX_IMAGE_SIZE) {
                                    message = '图片大小不能超过5MB';
                                }

                                flash(message);
                            },
                            customInsert(res, insertFn) {
                                if (res.code == 1) {
                                    insertFn(res.url);
                                } else {
                                    alert(res.msg || '上传失败');
                                }
                            }
                        },
                    },
                    customPaste: customPasteHandler,
                },
                mode: 'default',
            });

            createToolbar({
                editor: mainEditor,
                selector: '#writer-toolbar',
                mode: 'default',
            });

            if (mainEditor.onChange) {
                mainEditor.onChange(() => {
                    // 标记内容已修改
                    markContentAsModified();
                });
            }
        } else {
            console.warn('wangEditor 未加载，使用简易编辑器');
        }
    }

    function initSteps() {
        const stepsContainer = document.getElementById('steps-container');
        if (stepsContainer && window.StepsComponent) {
            window.StepsComponent.mount(stepsContainer, {
                active: 3,
                variant: 'workspace',
                routes: {
                    1: `/project_document/outline-draft`,
                    2: `/project_document/outline-confirm/${documentId}`,
                    3: null,
                    4: `/project_document/preview-review/${documentId}?mode=editable`,
                },
                onCurrent: () => flash('当前已在智能写作'),
            });
        }
    }

    function initPanelStates() {
        const panels = {
            outline: document.querySelector('.outline-panel'),
            review: document.querySelector('.review-section'),
            notes: document.querySelector('.notes-panel'),
            ai: document.querySelector('.ai-panel')
        };

        Object.keys(panels).forEach(panelKey => {
            const panel = panels[panelKey];
            if (!panel) return;

            const savedState = localStorage.getItem(`panel_${panelKey}_collapsed`);
            if (savedState === 'true') {
                panel.classList.add('collapsed');
            }
        });

        // 恢复CSS变量
        restoreCssVars();

        const historyToggle = document.getElementById('toggle-ai-panel');
        if (historyToggle) {
            const savedHistoryState = localStorage.getItem('ai_history_open');
            if (savedHistoryState === 'true') {
                historyToggle.classList.add('active');
                setHistoryOpen(true);
            }
        }
    }

    function restoreCssVars() {
        // 从sessionStorage恢复CSS变量
        const savedWidth = sessionStorage.getItem(CSS_VARS.OUTLINE_WIDTH);
        if (savedWidth) {
            setCssVar(CSS_VARS.OUTLINE_WIDTH, savedWidth);
        }
    }

    function saveCssVars() {
        // 保存CSS变量到sessionStorage
        const currentWidth = getCssVar(CSS_VARS.OUTLINE_WIDTH);
        if (currentWidth) {
            sessionStorage.setItem(CSS_VARS.OUTLINE_WIDTH, currentWidth);
        }
    }

    // ==================== 保存当前章节函数 ====================
    async function saveCurrentSection() {
        if (!currentSectionNodeId || isAutoSaving) return;

        try {
            isAutoSaving = true;

            let content = '';
            if (mainEditor) {
                if (typeof mainEditor.getHtml === 'function') {
                    content = mainEditor.getHtml();
                } else if (typeof mainEditor.getText === 'function') {
                    content = mainEditor.getText();
                }
            }

            const saveData = {
                content: content,
                key_point: workspaceData.editorData.writingPoint,
                status: 'writing'
            };

            await DataService.saveSectionContent(documentId, currentSectionNodeId, saveData);
            console.log('自动保存成功');
            return true;
        } catch (error) {
            console.error('保存章节失败:', error);
            return false;
        } finally {
            isAutoSaving = false;
        }
    }

    // ==================== 数据加载函数 ====================
    async function loadWorkspaceData() {
        try {
            workspaceData = await DataService.getWorkspaceData(documentId);
            processWorkspaceData();
            renderAllComponents();
            hideLoading();

            // 获取URL中的node_id参数
            const urlParams = new URLSearchParams(window.location.search);
            const nodeIdParam = urlParams.get('node_id');

            // 如果URL中有node_id参数，则尝试加载该节点
            if (nodeIdParam && workspaceData.outlineData) {
                // 查找节点是否存在于大纲中
                const targetNode = findNodeInOutline(nodeIdParam, workspaceData.outlineData);
                if (targetNode) {
                    await loadSectionContent(nodeIdParam);
                } else {
                    // 如果找不到对应节点，加载第一个章节的第一个节点
                    await loadFirstSection();
                }
            } else {
                // 如果没有node_id参数，加载第一个章节的第一个节点
                await loadFirstSection();
            }
        } catch (error) {
            console.error('加载工作区数据失败:', error);
            showError('加载数据失败: ' + error.message);
            hideLoading();
        }
    }

    // 在大纲数据中查找节点
    function findNodeInOutline(nodeId, outlineData) {
        if (!outlineData || !outlineData.chapters) {
            return null;
        }

        // 遍历所有章节
        for (const chapter of outlineData.chapters) {
            if (!chapter.sections) continue;

            // 检查章节内的节点
            for (const section of chapter.sections) {
                if (section.id === nodeId) {
                    return section;
                }

                // 检查子节点
                if (section.subsections) {
                    for (const subsection of section.subsections) {
                        if (subsection.id === nodeId) {
                            return subsection;
                        }
                    }
                }
            }
        }

        return null;
    }

    // 加载第一个章节的第一个节点
    async function loadFirstSection() {
        if (workspaceData.outlineData && workspaceData.outlineData.chapters.length > 0) {
            const firstChapter = workspaceData.outlineData.chapters[0];
            if (firstChapter.sections && firstChapter.sections.length > 0) {
                const firstSection = firstChapter.sections[0];
                await loadSectionContent(firstSection.id);
            }
        }
    }

    function processWorkspaceData() {
        if (!workspaceData) return;

        if (workspaceData.outlineData) {
            workspaceData.outlineData.headingTitle = workspaceData.outlineData.title || '全文立项标题';
        }

        if (workspaceData.editorData) {
            if (!Array.isArray(workspaceData.editorData.paragraphs)) {
                workspaceData.editorData.paragraphs = [];
            }
        }

        if (workspaceData.notesData) {
            // 注意：这里不使用workspaceData.notesData，而是从接口获取改进笔记
            // notesData = workspaceData.notesData;
        }

        if (workspaceData.aiTopicsData) {
            aiTopicsData = workspaceData.aiTopicsData.map((topic, idx) => ({
                ...topic,
                removable: idx < 3,
            }));
        }

        if (workspaceData.historyData) {
            historyData = workspaceData.historyData;
        }

        if (workspaceData.materialData) {
            materialData = workspaceData.materialData;
        }

        if (!workspaceData.quickActionsData) {
            workspaceData.quickActionsData = [
                { text: '帮我润色', isEdit: false },
                { text: '帮我打分', isEdit: false },
                { text: '帮我写作', isEdit: true },
                { text: '编辑对话', isEdit: true },
            ];
        }
    }

    async function loadSectionContent(nodeId) {
        try {
            const sectionData = await DataService.getSectionContent(documentId, nodeId);

            // 1. 先保存当前章节内容
            await saveCurrentSection();

            // 2. 销毁旧的编辑器实例
            if (mainEditor && mainEditor.destroy) {
                mainEditor.destroy();
                mainEditor = null;
            }

            currentSectionNodeId = nodeId;
            currentSectionLevel = sectionData.level; // 记录节点级别

            // 设置初始评审范围
            if (currentSectionLevel === 1) {
                // 章节节点，默认显示本章评审
                currentReviewScope = 'chapter';
                currentReviewNodeId = nodeId;
            } else {
                // 小节节点，默认显示本节评审
                currentReviewScope = 'section';
                currentReviewNodeId = nodeId;
            }

            updateSectionData(sectionData);

            // 3. 重新初始化编辑器
            setTimeout(() => {
                initEditor(); // 重新创建编辑器
                renderEditorContent();

                // 重置评审状态
                hasReviewed = false;
                isContentModified = false;
                originalEditorContent = '';
                lastReviewedNodeId = null;
                updateReviewButtonState();
            }, 10); // 小延迟确保DOM更新

            // 4. 加载评审数据
            await loadReviewData(currentReviewNodeId);

            // 5. 加载改进笔记列表（未删除）
            await loadImprovementDrafts();

            // 6. 更新左侧大纲选中状态
            updateOutlineSelectionByNodeId(nodeId);

            // 7. 更新合并按钮文本和状态 - 默认按小节显示
            currentMergeButtonType = 'section';
            updateMergeButton();

            // 8. 更新评审范围按钮状态
            updateReviewScopeButtons();

            // 9. 加载已删除的改进笔记（历史对话）
            await loadDeletedImprovementDrafts();

            flash('章节已加载');
        } catch (error) {
            console.error('加载章节内容失败:', error);
            flash('加载章节失败: ' + error.message);
        }
    }

    function updateSectionData(sectionData) {
        if (!sectionData || !workspaceData) return;

        workspaceData.editorData = {
            chapterTitle: sectionData.chapterTitle || '',
            writingPoint: sectionData.writingPoint || '',
            sectionTitle: sectionData.sectionTitle || '',
            paragraphs: sectionData.content ? [sectionData.content] : ['请开始写作...']
        };

        // 不再在此处设置评审数据，而是通过loadReviewData函数加载
    }

    // ==================== 改进笔记相关函数 ====================
    async function loadImprovementDrafts() {
        try {
            if (!documentId || !currentReviewNodeId) return;

            const result = await DataService.getImprovementDrafts(
                documentId,
                currentReviewNodeId,
                null,  // source_type
                false, // is_merged
                false  // is_deleted为false，获取未删除的笔记
            );

            if (result && result.drafts) {
                improvementDrafts = result.drafts;
                renderImprovementDrafts();
            } else {
                improvementDrafts = [];
                renderImprovementDrafts();
            }
        } catch (error) {
            console.error('获取改进笔记列表失败:', error);
            flash('获取改进笔记失败: ' + error.message);
            improvementDrafts = [];
            renderImprovementDrafts();
        }
    }

    // 加载已删除的改进笔记（用于历史对话区域）
    async function loadDeletedImprovementDrafts() {
        try {
            if (!documentId || !currentReviewNodeId) return;

            const result = await DataService.getImprovementDrafts(
                documentId,
                currentReviewNodeId,
                null,  // source_type
                null,  // is_merged
                true   // is_deleted为true，获取已删除的笔记
            );

            if (result && result.drafts) {
                deletedImprovementDrafts = result.drafts;
                renderHistory(); // 重新渲染历史对话区域
            } else {
                deletedImprovementDrafts = [];
                renderHistory();
            }
        } catch (error) {
            console.error('获取已删除改进笔记列表失败:', error);
            deletedImprovementDrafts = [];
            renderHistory();
        }
    }

    // 绑定改进笔记点击事件，用于加载对话历史
    function bindImprovementDraftEvents() {
        const container = document.getElementById('notes-content');
        if (!container) return;

        // 使用事件委托处理改进笔记点击
        container.addEventListener('click', async (e) => {
            // 查找点击的笔记项
            const noteItem = e.target.closest('.note-item');
            if (!noteItem) return;

            // 获取草稿ID
            const draftId = noteItem.getAttribute('data-draft-id');
            if (!draftId) return;

            // 加载该草稿对应的对话消息
            await loadDraftConversationToAIPanel(parseInt(draftId));
        });
    }

    // 加载改进草稿的对话消息到AI面板
    async function loadDraftConversationToAIPanel(draftId) {
        try {
            if (!documentId || !currentReviewNodeId || !draftId) return;

            // 调用接口获取对话消息
            const conversationData = await DataService.getConversationMessages(
                documentId,
                currentReviewNodeId,
                draftId
            );

            if (!conversationData || !conversationData.messages) {
                flash('未找到对话记录');
                return;
            }

            // 清空当前聊天记录
            chatMessages = [];

            // 转换消息格式
            conversationData.messages.forEach(msg => {
                const message = {
                    type: msg.role === 'user' ? 'user' : 'ai',
                    text: msg.content || '',
                    message_type: msg.message_type || 'text',
                    created_at: msg.created_at,
                    id: msg.messageId,
                    sessionId: msg.session_id || conversationData.sessionId
                };

                // 处理附件
                if (msg.attachments && msg.attachments.length > 0) {
                    message.attachments = msg.attachments.map(attach => ({
                        name: attach.filename,
                        url: attach.file_url,
                        text: attach.text,
                        image_url: attach.image_url,
                        icon: attach.image_url ?
                            '/static/project_document/images/writing-workspace/icon-file-preview.png' :
                            '/static/project_document/images/writing-workspace/icon-uploaded-file.svg'
                    }));
                }

                chatMessages.push(message);
            });

            // 设置当前会话ID
            currentSessionId = conversationData.sessionId;

            // 切换到聊天状态
            switchToChatState();
            renderChatMessages();

            // 显示改进草稿的原始内容作为第一条消息（如果没有对话消息）
            if (conversationData.improvementContent && chatMessages.length === 0) {
                chatMessages.push({
                    type: 'user',
                    text: conversationData.improvementContent
                });

                if (conversationData.helpText) {
                    chatMessages.push({
                        type: 'ai',
                        text: conversationData.helpText
                    });
                }

                renderChatMessages();
            }

            flash('对话历史已加载');
        } catch (error) {
            console.error('加载对话历史失败:', error);
            flash('加载对话历史失败: ' + error.message);
        }
    }

    // 加载改进笔记
    function renderImprovementDrafts() {
        const container = document.getElementById('notes-content');
        if (!container) return;

        if (!improvementDrafts || improvementDrafts.length === 0) {
            container.innerHTML = `
                <div class="notes-empty" style="display: block;">
                    <span class="secondary-text">暂无改进笔记</span>
                </div>
            `;
            // 当没有改进笔记时，禁用合并按钮
            updateMergeButtonState(false);
            return;
        }

        // 清空容器
        container.innerHTML = '';

        // 创建笔记列表容器
        const notesList = document.createElement('div');
        notesList.className = 'notes-list';
        container.appendChild(notesList);

        // 渲染每个改进笔记
        improvementDrafts.forEach((draft, index) => {
            const noteItem = document.createElement('div');
            noteItem.className = 'mt-space-twenty flex-row justify-evenly notes-checkbox-container note-item';
            noteItem.setAttribute('data-draft-id', draft.id);
            noteItem.setAttribute('title', '点击查看完整对话历史');

            // 复选框
            const checkbox = document.createElement('div');
            checkbox.className = `notes-checkbox ${draft.is_selected ? 'checked' : ''}`;
            checkbox.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleDraftSelection(draft.id, !draft.is_selected);
            });

            // 笔记内容 - 包装在可点击区域中
            const contentWrapper = document.createElement('div');
            contentWrapper.className = 'draft-content-wrapper';
            contentWrapper.style.flex = '1';
            contentWrapper.style.cursor = 'pointer';
            contentWrapper.style.display = 'flex';
            contentWrapper.style.alignItems = 'center';

            const contentSpan = document.createElement('span');
            contentSpan.className = 'secondary-text notes-text-line-height';
            // 显示前50个字符，超过则显示...
            const displayText = draft.content || draft.help_text || '无内容';
            contentSpan.textContent = displayText.length > 50 ?
                displayText.substring(0, 50) + '...' : displayText;
            contentSpan.style.flex = '1';

            contentWrapper.appendChild(contentSpan);

            // 添加点击事件
            contentWrapper.addEventListener('click', async (e) => {
                e.stopPropagation();
                // 显示加载中提示
                const originalText = contentSpan.textContent;
                contentSpan.textContent = '加载中...';

                try {
                    await loadDraftConversationToAIPanel(draft.id);
                    contentSpan.textContent = originalText;
                } catch (error) {
                    contentSpan.textContent = originalText;
                    console.error('加载对话失败:', error);
                }
            });

            // 删除按钮
            const deleteBtn = document.createElement('img');
            deleteBtn.className = 'icon-medium';
            deleteBtn.src = '/static/project_document/images/common/icon-delete.png';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.setAttribute('title', '删除');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                openDeleteModal({
                    type: 'improvement_draft',
                    draftId: draft.id,
                    title: '确定删除该改进笔记吗？'
                });
            });

            // 会话标识图标
            noteItem.appendChild(checkbox);
            noteItem.appendChild(contentWrapper);
            noteItem.appendChild(deleteBtn);
            notesList.appendChild(noteItem);
        });

        // 绑定事件
        bindImprovementDraftEvents();

        // 更新合并按钮状态
        updateMergeButtonState(true);
    }

    // 更新合并按钮状态
    function updateMergeButtonState(hasDrafts) {
        const mergeBtn = document.getElementById('merge-btn');
        if (!mergeBtn) return;

        if (!hasDrafts) {
            // 没有改进笔记时，按钮置灰
            mergeBtn.style.opacity = '0.5';
            mergeBtn.style.cursor = 'not-allowed';
            mergeBtn.onclick = null;
            mergeBtn.setAttribute('title', '暂无改进笔记可合入');
        } else {
            // 有改进笔记时，按钮可点击
            mergeBtn.style.opacity = '1';
            mergeBtn.style.cursor = 'pointer';
            mergeBtn.removeAttribute('title');
        }
    }

    async function toggleDraftSelection(draftId, isSelected) {
        try {
            // 这里可以调用后端接口更新选中状态
            // 暂时只更新本地状态
            const draft = improvementDrafts.find(d => d.id === draftId);
            if (draft) {
                draft.is_selected = isSelected;
                renderImprovementDrafts();
                flash(isSelected ? '已选中笔记' : '已取消选中');
            }
        } catch (error) {
            console.error('更新笔记选中状态失败:', error);
            flash('操作失败: ' + error.message);
        }
    }

    function loadDraftToAIPanel(draft) {
        if (!draft) return;

        // 清空当前聊天记录
        chatMessages = [];

        // 添加改进笔记内容作为用户消息
        if (draft.content) {
            chatMessages.push({
                type: 'user',
                text: draft.content,
                timestamp: draft.created_at
            });
        }

        // 添加帮助文本作为AI消息（如果有）
        if (draft.help_text) {
            chatMessages.push({
                type: 'ai',
                text: draft.help_text,
                timestamp: draft.updated_at || draft.created_at
            });
        }

        // 切换到聊天状态
        switchToChatState();
        renderChatMessages();

        // 设置会话ID
        if (draft.session_id) {
            currentSessionId = draft.session_id;
        }
    }

    async function addImprovementDraft() {
        try {
            if (chatMessages.length === 0) {
                flash('当前没有对话内容可以加入改进笔记');
                return;
            }

            // 找到第一条用户消息
            const firstUserMsg = chatMessages.find(msg => msg.type === 'user');
            if (!firstUserMsg) {
                flash('没有找到用户消息');
                return;
            }

            // 找到第一条AI回复
            const firstAiMsg = chatMessages.find(msg => msg.type === 'ai');

            // 准备数据
            const draftData = {
                document_id: documentId,
                node_id: currentReviewNodeId,
                session_id: currentSessionId || `session_${Date.now()}`,
                source_type: 'help',  // 来源类型：help表示AI帮助
                content: firstUserMsg.text,
                help_text: firstAiMsg ? firstAiMsg.text : '',
                is_selected: false,
                is_merged: false
            };

            // 调用接口
            const result = await DataService.addImprovementDraft(draftData);

            if (result && result.id) {
                flash('已加入改进笔记');

                // 重新加载改进笔记列表
                await loadImprovementDrafts();

                // 结束本轮对话（可选）
                // switchToInitialState();
            } else {
                flash('加入改进笔记失败');
            }
        } catch (error) {
            console.error('加入改进笔记失败:', error);
            flash('加入改进笔记失败: ' + error.message);
        }
    }

    // 删除改进笔记
    async function deleteImprovementDraft(draftId) {
        try {
            // 调用后端接口删除
            await DataService.deleteImprovementDraft(draftId);

            // 更新本地状态
            improvementDrafts = improvementDrafts.filter(d => d.id !== draftId);
            renderImprovementDrafts();

            // 更新合并按钮状态
            updateMergeButtonState(improvementDrafts.length > 0);

            // 重新加载已删除的改进笔记（历史对话）
            await loadDeletedImprovementDrafts();

            flash('改进笔记已删除');

            // 如果当前AI面板显示的是被删除的草稿的对话，则重置AI面板
            if (currentSessionId) {
                const deletedDraft = improvementDrafts.find(d => d.session_id === currentSessionId);
                if (!deletedDraft) {
                    // 如果当前会话对应的草稿已被删除，重置AI面板
                    switchToInitialState();
                }
            }
        } catch (error) {
            console.error('删除改进笔记失败:', error);
            flash('删除失败: ' + error.message);
        }
    }

    // ==================== 合并进度处理函数 ====================
    function startMergeTimer() {
        stopMergeTimer();
        mergeSeconds = 0;

        const waitingArea = document.querySelector('#waitingArea');
        if (waitingArea) {
            waitingArea.style.display = 'block';
            const timeElement = waitingArea.querySelector('.review-waiting-time');
            if (timeElement) {
                timeElement.textContent = '00:00';
            }
        }

        mergeTimerInterval = setInterval(() => {
            mergeSeconds++;
            const minutes = Math.floor(mergeSeconds / 60);
            const seconds = mergeSeconds % 60;
            const formattedTime =
                minutes.toString().padStart(2, '0') + ':' +
                seconds.toString().padStart(2, '0');

            const timeElement = document.querySelector('#waitingArea .review-waiting-time');
            if (timeElement) {
                timeElement.textContent = formattedTime;
            }
        }, 1000);
    }

    function stopMergeTimer() {
        if (mergeTimerInterval) {
            clearInterval(mergeTimerInterval);
            mergeTimerInterval = null;
        }
    }

    function showMergeSuccess(mergedText) {
        const waitingArea = document.querySelector('#waitingArea');
        if (waitingArea) {
            waitingArea.innerHTML = `
                <div class="review-waiting-content">
                    <span class="review-waiting-time" style="color: #52c41a;">✓</span>
                    <div class="review-waiting-text">
                        <span style="color: #52c41a;">合并成功！即将跳转到对比页面...</span>
                    </div>
                </div>
            `;

            // 标记所有笔记为已合入
            improvementDrafts.forEach(draft => {
                draft.is_merged = true;
            });

            // 重新渲染改进笔记列表（清空列表）
            improvementDrafts = [];
            renderImprovementDrafts();

            // 2秒后跳转
            setTimeout(() => {
                closeConfirmMergeModal();
                DataService.navigateToPage(`/project_document/full-compare/${documentId}`, {
                    document_id: documentId,
                    node_id: currentReviewNodeId,
                    full_text: mergedText
                });
            }, 2000);
        }
    }

    function showMergeError(errorMessage) {
        const waitingArea = document.querySelector('#waitingArea');
        if (waitingArea) {
            waitingArea.innerHTML = `
                <div class="review-waiting-content">
                    <span class="review-waiting-time" style="color: #ff4d4f;">✗</span>
                    <div class="review-waiting-text">
                        <span style="color: #ff4d4f;">合并失败: ${errorMessage}</span>
                        <div style="margin-top: 10px;">
                            <button class="merge-retry-btn btn btn-primary" id="merge-retry-btn">重试</button>
                            <button class="merge-cancel-btn btn btn-secondary" id="merge-cancel-btn">取消</button>
                        </div>
                    </div>
                </div>
            `;

            // 绑定重试按钮事件
            const retryBtn = document.getElementById('merge-retry-btn');
            const cancelBtn = document.getElementById('merge-cancel-btn');

            if (retryBtn) {
                retryBtn.addEventListener('click', () => {
                    startMergeProcess();
                });
            }

            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    closeConfirmMergeModal();
                });
            }
        }
    }

    async function startMergeProcess() {
        try {
            isMerging = true;

            // 隐藏按钮，显示等待区域
            const buttons = document.querySelector('.unmerged-modal-buttons');
            if (buttons) {
                buttons.style.display = 'none';
            }

            // 开始计时
            startMergeTimer();

            // 获取所有改进笔记的ID（包括未合入和已选中的）
            const allDraftIds = improvementDrafts.map(draft => draft.id);

            if (allDraftIds.length === 0) {
                stopMergeTimer();
                showMergeError('没有可合入的改进笔记');
                return;
            }

            // 准备合并数据 - 使用所有draft的id
            const mergeData = {
                document_id: documentId,
                node_id: currentReviewNodeId,
                draft_ids: allDraftIds  // 改为draft_ids参数
            };

            console.log('合并请求数据:', mergeData);

            // 调用合并接口
            const result = await DataService.mergeDrafts(mergeData);

            // 根据新的返回数据结构调整处理逻辑
            if (result && result.texts && result.texts.length > 0) {
                const mergedText = result.texts[0].text; // 获取第一个文本项的内容
                stopMergeTimer();
                showMergeSuccess(mergedText);
                flash('改进笔记已成功合入正文');
            } else {
                throw new Error('合入失败：未返回有效的文本内容');
            }
        } catch (error) {
            console.error('合入改进笔记失败:', error);
            stopMergeTimer();
            showMergeError(error.message);
        } finally {
            isMerging = false;
        }
    }

    // 绑定确认弹窗事件
    function bindConfirmMergeModalEvents() {
        const confirmMergeModalOverlay = document.getElementById('regenerate-confirm-overlay');
        const confirmMergeCancel = document.getElementById('regenerate-confirm-cancel');
        const confirmMergeContinue = document.getElementById('regenerate-confirm-continue');

        if (!confirmMergeModalOverlay || !confirmMergeCancel || !confirmMergeContinue) {
            console.warn('合并确认弹窗元素未找到');
            return;
        }

        // 取消按钮
        confirmMergeCancel.addEventListener('click', () => {
            closeConfirmMergeModal();
            flash('已取消合并操作');
        });

        // 继续按钮 - 修改：不关闭弹窗，开始合并过程
        confirmMergeContinue.addEventListener('click', () => {
            if (isMerging) return;
            startMergeProcess();
        });

        // 点击遮罩层关闭
        confirmMergeModalOverlay.addEventListener('click', (e) => {
            if (e.target === confirmMergeModalOverlay && !isMerging) {
                closeConfirmMergeModal();
                flash('已取消合并操作');
            }
        });
    }

    // 关闭确认弹窗并重置状态
    function closeConfirmMergeModal() {
        const confirmModalOverlay = document.getElementById('regenerate-confirm-overlay');
        if (confirmModalOverlay) {
            confirmModalOverlay.classList.remove('show');

            // 重置等待区域
            const waitingArea = confirmModalOverlay.querySelector('#waitingArea');
            if (waitingArea) {
                waitingArea.style.display = 'none';
                waitingArea.innerHTML = `
                    <img class="review-waiting-clock" src="/static/project_document/images/writing-workspace/review-waiting-clock.png">
                    <div class="review-waiting-content">
                      <span class="review-waiting-time">00:00</span>
                      <div class="review-waiting-text">
                        <span>AI正在生成正文，请耐心等待</span>
                        <span>大约 1～3 分钟完成评估</span>
                      </div>
                    </div>
                `;
            }

            // 显示按钮
            const buttons = confirmModalOverlay.querySelector('.unmerged-modal-buttons');
            if (buttons) {
                buttons.style.display = 'flex';
            }
        }

        // 停止计时器
        stopMergeTimer();
        isMerging = false;
    }

    async function mergeSelectedDrafts() {
        try {
            // 获取所有改进笔记的ID（包括未合入和已选中的）
            const allDraftIds = improvementDrafts.map(draft => draft.id);

            if (allDraftIds.length === 0) {
                flash('没有可合入的改进笔记');
                return;
            }

            // 准备合并数据 - 使用所有draft的id
            const mergeData = {
                document_id: documentId,
                node_id: currentReviewNodeId,
                draft_ids: allDraftIds  // 改为draft_ids参数
            };

            console.log('合并请求数据:', mergeData);

            // 调用合并接口
            const result = await DataService.mergeDrafts(mergeData);

            // 根据新的返回数据结构调整处理逻辑
            if (result && result.texts && result.texts.length > 0) {
                const mergedText = result.texts[0].text; // 获取第一个文本项的内容

                flash('正文已经生成，将跳转到比对页面。');
                // 标记所有笔记为已合入
                improvementDrafts.forEach(draft => {
                    draft.is_merged = true;
                });

                // 重新渲染改进笔记列表（清空列表）
                improvementDrafts = [];
                renderImprovementDrafts();

                setTimeout(() => {
                   DataService.navigateToPage(`/project_document/full-compare/${documentId}`, { document_id: documentId, node_id: currentReviewNodeId, full_text:mergedText });
                }, 2000);

                flash('改进笔记已成功合入正文');
            } else {
                flash('合入失败：未返回有效的文本内容');
            }
        } catch (error) {
            console.error('合入改进笔记失败:', error);
            flash('合入失败: ' + error.message);
        }
    }
    // ==================== 改进笔记相关函数 结束 ====================

    // ==================== 渲染函数 ====================
    function renderAllComponents() {
        if (!workspaceData) return;

        renderOutline(workspaceData.outlineData);
        renderEditorContent();

        // 不再使用原有的notesData，改用improvementDrafts
        renderAiTopics(aiTopicsData);
        renderMaterialGrid();
        updateMergeButton();
        renderHistory();

        // 更新评审按钮状态
        updateReviewButtonState();
    }

    function renderOutline(data) {
        const container = document.getElementById('outline-content');
        if (!container || !data) return;

        let html = `
            <div class="outline-row outline-row-title">
                <span class="outline-item-text outline-item-line-height outline-title-label" title=${data.headingTitle || '全文立项标题'}>${data.headingTitle || '全文立项标题'}</span>
                <img style="display:none" class="ml-space-six shrink-0 outline-item-icon outline-title-edit" src="/static/project_document/images/writing-workspace/edit.png" />
            </div>
        `;

        if (data.chapters && data.chapters.length > 0) {
            data.chapters.forEach((chapter, chapterIndex) => {
                const isActive = false; // 初始不设置任何章节为active
                const chapterClass = 'outline-row-chapter';

                html += `
                    <div class="${chapterClass}" data-chapter-index="${chapterIndex}">
                        <span class="outline-item-text chapter-name-line-height" title="${chapter.id || ''} ${chapter.name || ''}">${chapter.id || ''} ${chapter.name || ''}</span>
                    </div>
                `;

                if (chapter.sections && chapter.sections.length > 0) {
                    chapter.sections.forEach((section, idx) => {
                        html += `
                            <div class="outline-row outline-row-hover outline-row-clickable outline-level-section"
                                 data-chapter="${chapter.name || ''}"
                                 data-section="${section.id || ''}"
                                 data-title="${section.title || ''}"
                                 title="${section.title || ''}"
                                 data-chapter-index="${chapterIndex}"
                                 data-section-index="${idx}">
                                <span class="secondary-text outline-text-ellipsis">${section.id || ''} ${section.title || ''}</span>
                            </div>
                        `;

                        if (section.subsections && section.subsections.length > 0) {
                            section.subsections.forEach((sub, subIndex) => {
                                html += `
                                    <div class="outline-row outline-row-hover outline-row-clickable outline-level-subsection"
                                         data-chapter="${chapter.name || ''}"
                                         data-section="${sub.id || ''}"
                                         data-title="${sub.title || ''}"
                                         title="${sub.title || ''}"
                                         data-chapter-index="${chapterIndex}"
                                         data-section-index="${idx}"
                                         data-sub-index="${subIndex}">
                                        <span class="secondary-text outline-text-ellipsis">${sub.id || ''} ${sub.title || ''}</span>
                                    </div>
                                `;
                            });
                        }
                    });
                }
            });
        } else {
            html += `
                <div class="outline-row">
                    <span class="secondary-text">暂无大纲数据</span>
                </div>
            `;
        }

        container.innerHTML = html;
        bindOutlineEvents();
    }

    // ==================== 根据节点ID更新大纲选中状态 ====================
    function updateOutlineSelectionByNodeId(nodeId) {
        const container = document.getElementById('outline-content');
        if (!container) return;

        // 清除所有选中状态
        container.querySelectorAll('.outline-row-chapter.outline-row-active').forEach(el => {
            el.classList.remove('outline-row-active');
        });

        container.querySelectorAll('.outline-row-clickable').forEach(el => {
            el.classList.remove('outline-row-selected');
        });

        // 查找对应的章节和节点
        let foundChapter = null;
        let foundNode = null;

        // 先尝试查找精确匹配的节点
        const exactNode = container.querySelector(`.outline-row-clickable[data-section="${nodeId}"]`);
        if (exactNode) {
            foundNode = exactNode;
            // 获取对应的章节
            const chapterIndex = exactNode.dataset.chapterIndex;
            if (chapterIndex !== undefined) {
                foundChapter = container.querySelector(`.outline-row-chapter[data-chapter-index="${chapterIndex}"]`);
            }
        } else {
            // 如果没有精确匹配，可能是章节ID或者部分匹配
            // 查找章节ID
            const chapterId = nodeId.split('.')[0]; // 获取章节部分，如 "1.1" 中的 "1"
            const chapterNode = container.querySelector(`.outline-row-chapter[data-chapter-index="${parseInt(chapterId) - 1}"]`);
            if (chapterNode) {
                foundChapter = chapterNode;
            }

            // 查找最接近的节点（可能是父级节点）
            const allNodes = container.querySelectorAll('.outline-row-clickable');
            for (let node of allNodes) {
                const sectionId = node.dataset.section;
                if (sectionId && nodeId.startsWith(sectionId)) {
                    foundNode = node;
                    break;
                }
            }
        }

        // 设置选中状态
        if (foundChapter) {
            foundChapter.classList.add('outline-row-active');
            // 更新当前章节索引
            currentChapterIndex = parseInt(foundChapter.dataset.chapterIndex) || 0;
        }

        if (foundNode) {
            foundNode.classList.add('outline-row-selected');

            // 确保章节也选中
            const chapterIndex = foundNode.dataset.chapterIndex;
            if (chapterIndex !== undefined && !foundChapter) {
                const chapterEl = container.querySelector(`.outline-row-chapter[data-chapter-index="${chapterIndex}"]`);
                if (chapterEl) {
                    chapterEl.classList.add('outline-row-active');
                    currentChapterIndex = parseInt(chapterIndex) || 0;
                }
            }
        }

        // 如果当前是章节要点标签页，更新章节要点内容
        if (activeTab === 'chapter-points') {
            renderChapterPoints();
        }
    }

    function bindOutlineEvents() {
        const container = document.getElementById('outline-content');
        if (!container) return;

        container.querySelectorAll('.outline-row-chapter').forEach(item => {
            item.style.cursor = 'pointer';
            item.addEventListener('click', async () => {
                const index = parseInt(item.dataset.chapterIndex, 10);
                if (isNaN(index)) return;

                // 保存当前章节内容
                await saveCurrentSection();

                // 更新当前选中章节索引
                currentChapterIndex = index;

                const chapter = workspaceData.outlineData.chapters[index];
                if (!chapter || !chapter.sections || chapter.sections.length === 0) return;

                const firstSection = chapter.sections[0];

                // 更新URL参数
                updateUrlWithNodeId(firstSection.id);

                await loadSectionContent(firstSection.id);

                // 如果当前是章节要点标签页，更新章节要点内容
                if (activeTab === 'chapter-points') {
                    renderChapterPoints();
                }
            });
        });

        container.querySelectorAll('.outline-level-section, .outline-level-subsection').forEach(item => {
            item.style.cursor = 'pointer';
            item.addEventListener('click', async () => {
                // 保存当前章节内容
                await saveCurrentSection();

                const sectionId = item.dataset.section;
                const chapterIndex = parseInt(item.dataset.chapterIndex, 10);

                if (!sectionId) return;

                // 更新当前选中章节索引
                currentChapterIndex = chapterIndex;

                // 更新URL参数
                updateUrlWithNodeId(sectionId);

                await loadSectionContent(sectionId);

                // 如果当前是章节要点标签页，更新章节要点内容
                if (activeTab === 'chapter-points') {
                    renderChapterPoints();
                }
            });
        });

        const titleEditBtn = container.querySelector('.outline-title-edit');
        const titleLabel = container.querySelector('.outline-title-label');

        if (titleEditBtn && titleLabel) {
            titleEditBtn.addEventListener('click', () => {
                toggleTitleEditMode(titleLabel, true);
            });

            titleLabel.addEventListener('click', () => {
                toggleTitleEditMode(titleLabel, false);
            });
        }
    }

    // 更新URL参数函数
    function updateUrlWithNodeId(nodeId) {
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set('node_id', nodeId);

        const newUrl = `${window.location.pathname}?${urlParams.toString()}`;
        window.history.pushState({}, '', newUrl);
    }

    function toggleTitleEditMode(titleElement, forceEdit = false) {
        if (titleElement.isContentEditable) {
            titleElement.contentEditable = false;
            titleElement.classList.remove('outline-title-editing');

            const newTitle = titleElement.textContent.trim();
            if (newTitle && newTitle !== workspaceData.outlineData.headingTitle) {
                workspaceData.outlineData.headingTitle = newTitle;
                saveOutlineTitle(newTitle);
                // 内容已修改
                markContentAsModified();
            }
        } else if (forceEdit) {
            titleElement.contentEditable = true;
            titleElement.classList.add('outline-title-editing');
            titleElement.focus();

            const originalTitle = titleElement.textContent;
            titleElement.dataset.originalTitle = originalTitle;

            const handleKeyDown = (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    titleElement.blur();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    titleElement.textContent = originalTitle;
                    titleElement.blur();
                }
            };

            const handleBlur = () => {
                titleElement.contentEditable = false;
                titleElement.classList.remove('outline-title-editing');
                titleElement.removeEventListener('keydown', handleKeyDown);
                titleElement.removeEventListener('blur', handleBlur);
            };

            titleElement.addEventListener('keydown', handleKeyDown);
            titleElement.addEventListener('blur', handleBlur);
        }
    }

    async function saveOutlineTitle(newTitle) {
        try {
            flash('标题已更新');
        } catch (error) {
            console.error('保存标题失败:', error);
            flash('保存标题失败');
        }
    }

    // ==================== 章节要点渲染函数 ====================
    function renderChapterPoints() {
        const container = document.getElementById('chapter-points-content');
        if (!container || !workspaceData || !workspaceData.outlineData) {
            return;
        }

        // 获取当前选中的章节
        let chapter;
        if (currentChapterIndex >= 0 && currentChapterIndex < workspaceData.outlineData.chapters.length) {
            chapter = workspaceData.outlineData.chapters[currentChapterIndex];
        } else {
            // 如果没有选中的章节，显示第一个章节
            chapter = workspaceData.outlineData.chapters[0];
            currentChapterIndex = 0;
        }

        if (!chapter) {
            container.innerHTML = '<span class="secondary-text outline-title-margin">暂无章节要点</span>';
            return;
        }

        // 创建章节要点内容
        let content = `
            <div class="chapter-points-header">
                <h3 class="chapter-points-title">${chapter.name || '未命名章节'}</h3>
                <div class="chapter-points-id">章节 ID: ${chapter.id || '未知'}</div>
            </div>
        `;

        if (chapter.key_point && chapter.key_point.trim()) {
            content += `
                <div class="chapter-points-content scrollbar-custom">
                    ${chapter.key_point}
                </div>
            `;
        } else {
            content += `
                <div class="chapter-points-empty">
                    <span class="secondary-text">本章节暂无要点内容</span>
                </div>
            `;
        }

        container.innerHTML = content;
    }

    function renderEditorContent() {
        if (!workspaceData || !workspaceData.editorData) return;

        const chapterTitleEl = document.getElementById('chapter-title');
        const writingPointEl = document.getElementById('writing-point');

        if (chapterTitleEl) {
            chapterTitleEl.textContent = workspaceData.editorData.sectionTitle;
        }

        if (writingPointEl) {
            writingPointEl.innerHTML = workspaceData.editorData.writingPoint;
        }

        if (mainEditor) {
            // 检查内容是否为Markdown格式并转换
            let contentToRender = '';
            if (workspaceData.editorData.paragraphs && workspaceData.editorData.paragraphs.length > 0) {
                contentToRender = workspaceData.editorData.paragraphs.join('');

                // 处理Markdown内容
                contentToRender = processEditorContent(contentToRender);
            } else {
                contentToRender = '请开始写作...';
            }
            try {
                if (mainEditor.setHtml) {
                    mainEditor.setHtml(contentToRender);
                } else if (mainEditor.setText) {
                    mainEditor.setText(contentToRender);
                }
            }
            catch (error) {
                console.error('渲染编辑器数据失败:', error);
            }
            // 设置编辑器内容
        } else {
            const editorContainer = document.getElementById('editor-content');
            if (editorContainer) {
                // 检查内容是否为Markdown格式并转换
                let contentToRender = '';
                if (workspaceData.editorData.paragraphs && workspaceData.editorData.paragraphs.length > 0) {
                    contentToRender = workspaceData.editorData.paragraphs.join('');

                    // 处理Markdown内容
                    contentToRender = processEditorContent(contentToRender);
                } else {
                    contentToRender = '请开始写作...';
                }

                editorContainer.innerHTML = contentToRender;
            }
        }
    }

    function buildEditorHtml(data) {
        if (!data) return '';

        let html = '';

        if (data.paragraphs && data.paragraphs.length > 0) {
            data.paragraphs.forEach(paragraph => {
                if (typeof paragraph === 'string') {
                    html += `${paragraph}`;
                } else if (paragraph && typeof paragraph === 'object') {
                    const text = paragraph.text || '';
                    if (paragraph.type === 'h3') {
                        html += `<h3 class="chapter-heading chapter-heading-level-2">${text}</h3>`;
                    } else if (paragraph.type === 'h4') {
                        html += `<h4 class="chapter-heading chapter-heading-level-3">${text}</h4>`;
                    } else {
                        html += `${text}`;
                    }
                }
            });
        } else {
            html += '<p class="editor-text editor-text-justify">请开始写作...</p>';
        }

        return html;
    }

    // ==================== 评审数据加载函数 ====================
    async function loadReviewData(nodeId) {
        try {
            // 获取节点评审数据
            const sectionData = await DataService.getSectionContent(documentId, nodeId);

            // 更新当前评审节点ID
            currentReviewNodeId = nodeId;

            // 渲染评审数据
            renderReviewData(sectionData);

            console.log(`已加载节点 ${nodeId} 的评审数据`);
        } catch (error) {
            console.error('加载评审数据失败:', error);
            flash('加载评审数据失败: ' + error.message);
        }
    }

    function renderReview(data, scope = 'section') {
        if (!data) return;

        const scoreEl = document.getElementById('review-score');
        const subtitleEl = document.getElementById('review-subtitle');
        const contentEl = document.getElementById('review-content');

        if (scoreEl) {
            // 显示评分，不保留小数
            const score = data.score || 0;
            scoreEl.textContent = `评分 ${score}`; // 数据库中数据类型 为整数
        }
        if (subtitleEl) {
            // 根据评审范围显示不同的副标题
            if (scope === 'section') {
                subtitleEl.textContent = `小节评审结果 (满分${data.maxScore || 10}分)`;
            } else {
                subtitleEl.textContent = `本章评审结果 (满分${data.maxScore || 10}分)`;
            }
        }
        if (contentEl) {
            console.log(data)
            try {
                let contentHtml = setReviewContent(data, 'panel')
                contentEl.innerHTML = contentHtml || '<span class="content-text">暂无评审建议</span>';
            }
            catch (error) {
                contentEl.innerHTML = '<span class="content-text">暂无评审建议</span>';
            }
        }
    }

    // 切换章节时显示AI评审建议
    function renderReviewData(sectionData) {
        const reviewData = {
            score: sectionData.review_score || 0,
            maxScore: 10,
            evaluate: sectionData.review_data.evaluate ? sectionData.review_data.evaluate : "",
            suggestion: sectionData.review_data.suggestions ?
                sectionData.review_data.suggestions : []
        };
        renderReview(reviewData, currentReviewScope);

        // 更新评审详情内容
        nodeReviewDetailContent = setReviewContent(reviewData, 'detail');
    }

    function setReviewContent(reviewData, type = 'panel'){
        let contentHtml = ""

        if (type === 'detail' && reviewData.evaluate) {
            // 只在详情弹窗中显示专家点评
            const cleanEvaluate = reviewData.evaluate.replace(/\s+/g, ' ').trim();
            contentHtml += `<strong>专家点评：</strong><br />${cleanEvaluate}<br /><br />`;
        }

        // 添加建议内容 - 现在suggestion是数组
        if (reviewData.suggestion && Array.isArray(reviewData.suggestion) && reviewData.suggestion.length > 0) {
            // 面板和详情都需要显示改进建议
            contentHtml += `<strong>改进建议：</strong><br />`
            // 清理并处理每个建议项
            reviewData.suggestion.forEach((suggestion, index) => {
                if (suggestion && suggestion.trim()) {
                    const cleanSuggestion = suggestion.replace(/\s+/g, ' ').trim();
                    contentHtml += `<span class="content-text">${index + 1}. ${cleanSuggestion}<br /></span>`;
                }
            });
        }
        else{
            contentHtml = '<span class="content-text">暂无评审建议</span>';
        }
        return contentHtml
    }

    // 渲染评审接口返回的数据到页面 - 更新版
    function renderReviewFromResponse(reviewResponse, scope = 'section') {
        if (!reviewResponse || !reviewResponse.review) return;

        const reviewData = reviewResponse.review;
        // 1. 显示评分
        const scoreEl = document.getElementById('review-score');
        if (scoreEl && reviewData.score !== undefined) {
            // 去除小数，取整数部分
            const integerScore = reviewData.score;
            scoreEl.textContent = `评分 ${integerScore}`;
        }

        // 2. 显示评价和建议
        const contentEl = document.getElementById('review-content');
        if (contentEl) {
            let contentHtml = setReviewContent(reviewData, 'panel')
            contentEl.innerHTML = contentHtml || '<span class="content-text">暂无评审建议</span>';
        }

        // 3. 更新副标题 - 根据评审范围显示不同的文本
        const subtitleEl = document.getElementById('review-subtitle');
        if (subtitleEl) {
            if (scope === 'section') {
                subtitleEl.textContent = `小节评审结果 (满分${reviewData.maxScore || 10}分)`;
            } else {
                subtitleEl.textContent = `本章评审结果 (满分${reviewData.maxScore || 10}分)`;
            }
        }

        // 4. 显示待办列表到AI话题区域
        if (reviewData.to_do_list && Array.isArray(reviewData.to_do_list) && reviewData.to_do_list.length > 0) {
            console.log('更新AI话题列表:', reviewData.to_do_list);

            // 清空现有AI话题数据
            aiTopicsData = [];

            // 将待办列表转换为aiTopicsData格式
            reviewData.to_do_list.forEach((item, index) => {
                if (item && item.trim()) {
                    aiTopicsData.push({
                        id: Date.now() + index,
                        text: item.trim(),
                        removable: index < 3
                    });
                }
            });

            // 强制重新渲染AI话题区域
            renderAiTopics(aiTopicsData);

            // 更新工作区数据
            if (workspaceData) {
                workspaceData.aiTopicsData = [...aiTopicsData];
            }
        } else {
            // 如果没有待办列表，显示空状态
            aiTopicsData = [];
            renderAiTopics(aiTopicsData);
        }

        // 更新评审详情内容
        nodeReviewDetailContent = setReviewContent(reviewData, 'detail');
    }

    // ==================== 修改渲染AI话题函数 ====================
    function renderAiTopics(data) {
      const container = document.getElementById('ai-topics-content');
      if (!container) return;

      // 设置折叠状态类名
      if (aiTopicsCollapsed) {
        container.classList.add('collapsed');
      } else {
        container.classList.remove('collapsed');
      }

      if (!data || data.length === 0) {
        container.innerHTML = `
          <div class="ai-topic-empty">
            <span class="secondary-text">暂无AI话题</span>
          </div>
        `;
        return;
      }

      container.innerHTML = data.map((topic, index) => {
        const sectionClass = 'ai-topic-item';
        const arrowImg = '/static/project_document/images/writing-workspace/icon-topic-arrow.png';
        const tipsShow = topic.type ? `${topic.type}：${topic.text}` : topic.text;
        return `
          <div class="flex-row justify-between items-center ${sectionClass}"
               data-topic-index="${index}" title="${tipsShow}">
            <div class="flex-row items-center">
              <img class="shrink-0 ai-topic-icon"
                   src="/static/project_document/images/writing-workspace/icon-topic-bullet.png" />
              <div class="ai-topic-content ml-space-nine">
                <span class="secondary-text ai-topic-text">${tipsShow}</span>
              </div>
            </div>
            <img class="ai-topic-arrow" src="${arrowImg}" />
          </div>
        `;
      }).join('');
    }

    // ==================== 添加折叠/展开切换函数 ====================
    function toggleAiTopics() {
      aiTopicsCollapsed = !aiTopicsCollapsed;

      // 更新按钮状态
      const toggleBtn = document.getElementById('ai-topics-toggle');
      if (toggleBtn) {
        if (aiTopicsCollapsed) {
          toggleBtn.classList.add('collapsed');
          toggleBtn.setAttribute('title', '展开话题列表');
        } else {
          toggleBtn.classList.remove('collapsed');
          toggleBtn.setAttribute('title', '折叠话题列表');
        }
      }

      // 重新渲染AI话题区域
      renderAiTopics(aiTopicsData);

      // 保存状态到localStorage
      localStorage.setItem('ai_topics_collapsed', aiTopicsCollapsed.toString());

      flash(aiTopicsCollapsed ? 'AI话题已折叠' : 'AI话题已展开');
    }

    // ==================== 更新合并按钮函数 ====================
    function updateMergeButton() {
        const mergeBtn = document.getElementById('merge-btn');
        if (!mergeBtn) return;

        let buttonText = '';

        if (currentReviewNodeId && currentReviewNodeId.includes('.')) {
            // 小节模式：一键合入x.x章节正文
            buttonText = `一键合入${currentReviewNodeId}章节正文`;
        } else {
            // 章节模式：一键合入第x章正文
            buttonText = `一键合入第${currentReviewNodeId}章正文`;
        }

        mergeBtn.textContent = buttonText;

        // 更新按钮状态
        updateMergeButtonState(improvementDrafts && improvementDrafts.length > 0);
    }

    // ==================== 设置合并按钮类型函数 ====================
    function setMergeButtonType(type) {
        currentMergeButtonType = type;
        updateMergeButton();
    }

    // ==================== 更新评审范围按钮状态函数 ====================
    function updateReviewScopeButtons() {
        const thisSectionBtn = document.getElementById('thisSection');
        const thisChapterBtn = document.getElementById('thisChapter');

        if (!thisSectionBtn || !thisChapterBtn) return;

        // 清除所有active状态
        thisSectionBtn.classList.remove('active');
        thisChapterBtn.classList.remove('active');

        // 根据当前评审范围设置active状态
        if (currentReviewScope === 'section') {
            thisSectionBtn.classList.add('active');
        } else {
            thisChapterBtn.classList.add('active');
        }

        // 同时更新副标题
        const subtitleEl = document.getElementById('review-subtitle');
        if (subtitleEl) {
            if (currentReviewScope === 'section') {
                subtitleEl.textContent = `小节评审结果 (满分10分)`;
            } else {
                subtitleEl.textContent = `本章评审结果 (满分10分)`;
            }
        }
        const subtitleElDialog = document.getElementById('review-subtitle-dialog');
        if (subtitleElDialog) {
            if (currentReviewScope === 'section') {
                subtitleElDialog.textContent = `小节评审结果 (满分10分)`;
            } else {
                subtitleElDialog.textContent = `本章评审结果 (满分10分)`;
            }
        }

    }

    // ==================== AI帮助会话流式响应处理 ====================
    async function startAiHelpSessionWithStream(helpText) {
        try {
            // 生成会话ID
            const sessionId = currentSessionId || `help_${Date.now()}`;
            currentSessionId = sessionId;

            // 添加用户消息到聊天记录
            chatMessages.push({
                type: 'user',
                text: helpText
            });

            // 添加AI加载中消息（保存引用）
            const aiMessage = {
                type: 'ai',
                text: '',
                isStreaming: true
            };
            chatMessages.push(aiMessage);

            // 切换到聊天状态
            switchToChatState();
            renderChatMessages();

            // 使用新的流式响应服务
            const result = await DataService.startHelpSession({
                document_id: documentId,
                node_id: currentReviewNodeId,
                help_text: helpText
            });

            if (result.code !== 200 || !result.data || !result.data.stream) {
                throw new Error(result.message || 'AI帮助请求失败');
            }

            const { stream } = result.data;

            // 设置会话ID
            currentSessionId = sessionId;

            // 处理流式响应（兼容混合格式）
            await stream.process(
                // onChunk 回调：处理数据块
                (chunk) => {
                    // 尝试解析JSON
                    try {
                        const data = JSON.parse(chunk);
                        // 处理会话信息
                        if (data.session_id && data.message_id) {
                            currentSessionId = data.session_id;
                            currentMessageId = data.message_id;
                            // 保存message_id到AI消息对象
                            aiMessage.id = data.message_id;
                            return;
                        }
                    } catch (parseError) {
                        // 不是JSON，按文本处理
                    }

                    // 使用保存的引用更新AI消息
                    aiMessage.text += chunk;
                    aiMessage.isStreaming = true;
                    renderChatMessages();
                },
                // onComplete 回调：处理完成
                (completeData) => {
                    aiMessage.isStreaming = false;

                    // 更新会话ID和消息ID
                    if (completeData.session_id) {
                        currentSessionId = completeData.session_id;
                    }
                    if (completeData.message_id) {
                        currentMessageId = completeData.message_id;
                        aiMessage.id = completeData.message_id;
                    }

                    // 确保AI消息有sessionId
                    aiMessage.sessionId = currentSessionId;

                    renderChatMessages();

                    flash('AI帮助完成');
                },
                // onError 回调：错误处理
                (error) => {
                    console.error('AI帮助流式响应错误:', error);

                    // 移除加载中的消息
                    const index = chatMessages.findIndex(msg => msg === aiMessage);
                    if (index !== -1) {
                        chatMessages.splice(index, 1);
                    }
                    renderChatMessages();

                    flash('AI帮助请求失败: ' + error.message);
                }
            );

        } catch (error) {
            console.error('AI帮助请求失败:', error);

            // 移除加载中的消息
            const index = chatMessages.findIndex(msg => msg.isStreaming);
            if (index !== -1) {
                chatMessages.splice(index, 1);
            }
            renderChatMessages();

            flash('AI帮助请求失败: ' + error.message);
        }
    }

    // ==================== 修改历史对话渲染函数 ====================
    function renderHistory() {
        const historyContent = document.getElementById('ai-history-content');
        if (!historyContent) return;

        if (!deletedImprovementDrafts || deletedImprovementDrafts.length === 0) {
            historyContent.innerHTML = `
                <div class="ai-history-empty">
                    <span class="secondary-text">暂无已删除的改进笔记</span>
                </div>
            `;
            return;
        }

        historyContent.innerHTML = `
            <div class="ai-history-list">
                ${deletedImprovementDrafts.map((draft, index) => `
                    <div class="ai-history-item" data-draft-id="${draft.id}">
                        <div class="ai-history-item-content">
                            <span class="ai-history-item-text">${draft.content ? (draft.content.substring(0, 50) + (draft.content.length > 50 ? '...' : '')) : '无内容'}</span>
                            <div class="ai-history-item-meta">
                                <span class="ai-history-item-time">${formatDate(draft.deleted_at || draft.updated_at || draft.created_at)}</span>
                                <span class="ai-history-item-status">已删除</span>
                            </div>
                        </div>
                        <div class="ai-history-item-actions">
                            <img class="ai-history-view" title="查看对话历史" src="/static/images/register/eye-icon.svg" />
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        bindHistoryEvents();
    }

    // 日期格式化函数
    function formatDate(dateString) {
        if (!dateString) return '';
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            });
        } catch (e) {
            return '';
        }
    }

    function bindHistoryEvents() {
        const historyItems = document.querySelectorAll('.ai-history-item');
        historyItems.forEach(item => {
            // 点击整个项加载对话历史
            item.addEventListener('click', async (e) => {
                // 如果点击的是操作按钮，不触发
                if (e.target.closest('.ai-history-item-actions')) {
                    return;
                }

                const draftId = item.getAttribute('data-draft-id');
                if (draftId) {
                    await loadDraftConversationToAIPanel(parseInt(draftId));
                }
            });

            // 查看按钮点击事件
            const viewBtn = item.querySelector('.ai-history-view');
            if (viewBtn) {
                viewBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const draftId = item.getAttribute('data-draft-id');
                    if (draftId) {
                        await loadDraftConversationToAIPanel(parseInt(draftId));
                    }
                });
            }
        });
    }

    function loadHistoryToAIPanel(historyItem) {
        if (!historyItem) return;

        chatMessages = historyItem.dialogMessages || [];

        // 切换到聊天状态
        switchToChatState();
        renderChatMessages();

        flash('历史对话已加载');
    }

    function renderMaterialGrid() {
        const materialGrid = document.getElementById('material-modal-grid');
        if (!materialGrid) return;
        materialGrid.innerHTML = materialData.map(item => `
            <div class="material-grid-item">
                <img class="material-file-icon" src="${item.icon || '/static/project_document/images/common/icon-file-doc.png'}" />
                <span class="material-filename" file_id="${item.file_id}" file_url="${item.file_url}" file_name="${item.file_name || '未命名文件'}">${item.name || '未命名文件'}</span>
                <div class="material-action-group">
                    <img class="material-action-icon material-download-btn"
                         src="/static/project_document/images/common/icon-download.png" />
                    <img class="material-action-icon material-delete-btn"
                         src="/static/project_document/images/common/icon-delete.png"  />
                </div>
            </div>
        `).join('') + `
            <div class="material-grid-add" id="material-grid-add" style="display: none">
                <div class="material-add-wrapper">
                    <img class="material-add-icon"
                         src="/static/project_document/images/common/icon-add.png" />
                </div>
            </div>
            <div class="material-grid-upload" id="material-grid-upload">
                <img class="material-upload-icon"
                     src="/static/project_document/images/common/icon-upload-circle.png" />
                <span class="material-upload-label">点击或拖拽上传</span>
                <span class="material-upload-hint">100M以内的 PPT/word/PDF 文件</span>
            </div>
        `;

        bindMaterialEvents();
    }

    function bindMaterialEvents() {
        const downloadBtns = document.querySelectorAll('.material-download-btn');
        downloadBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const card = e.target.closest('.material-grid-item');
                const file_url = card.querySelector('.material-filename').getAttribute('file_url');
                const file_name = card.querySelector('.material-filename').getAttribute('file_name');
                if (file_url) {
                    downloadFileUrl(file_url,file_name);
                }
            });
        });

        const deleteBtns = document.querySelectorAll('.material-delete-btn');
        deleteBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const card = e.target.closest('.material-grid-item');
                const fileName = card.querySelector('.material-filename')?.textContent;
                const file_id = card.querySelector('.material-filename').getAttribute('file_id');
                openDeleteModal({
                    type: 'material',
                    fileName: fileName,
                    title: '确定删除该素材文件吗？',
                    file_id:file_id
                });
            });
        });

        const doneUploadFiles = (files) =>{
            Array.from(files).forEach(async (file) => {
                             let cardHtml = createUploadingCard(file.name)
                             $('#material-grid-upload').before(cardHtml);
                             const progressInterval = simulateUploadProgress(cardHtml, file);
                             const uploadResult = await uploadFileToServer(file,documentId);
                             clearInterval(progressInterval);
                             cardHtml.querySelector('.progress-text').progressText = '100%';
                             if (uploadResult.success) {
                                  const fileData = uploadResult.data;
                                  // 上传成功，移除上传中卡片，添加成功卡片
                                  cardHtml.remove();
                                  // 创建成功卡片
                                  const fileInfo = {
                                    name: fileData.name,
                                    original_name: fileData.original_name,
                                    url: fileData.url,
                                    file_path: fileData.file_path,
                                    unique_name: fileData.unique_name,
                                    mimeType: fileData.mimeType,
                                    size: fileData.size
                                  };
                                  uploadedFiles.push(fileInfo);
                                  const successCard = createSuccessCard(fileInfo);
                                   $('#material-grid-upload').before(successCard);
                                  flash(`上传成功：${file.name}`, 'success');
                            }
                        })
        }

        const uploadArea = document.getElementById('material-grid-upload');
        const addArea = document.getElementById('material-grid-add');
        const fileInput = document.getElementById('material-file-input');
        const materialGrid = document.getElementById('material-modal-grid');

        if (uploadArea && fileInput) {

            uploadArea.addEventListener('click', () => fileInput.click());

            fileInput.addEventListener('change', (e) => {
                  if (e.target.files.length) {
                      doneUploadFiles(e.target.files)
                  }
            });

            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('drag-over');
            });
            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('drag-over');
            });
            uploadArea.addEventListener('drop', async (e) => {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');

                const files = e.dataTransfer.files;
                if (files.length > 0) {
                   doneUploadFiles(files)
                    //await handleMaterialUpload(files[0]);
                }
            });
        }

        if (addArea && fileInput) {
            addArea.addEventListener('click', () => fileInput.click());
        }




    }



    async function handleMaterialUpload(file) {
        try {
            const result = await DataService.uploadFile(file);
            if (result.code === 200) {
                const newMaterial = {
                    name: file.name.length > 15 ? file.name.substring(0, 12) + '...' : file.name,
                    icon: getFileIcon(file.name)
                };

                materialData.push(newMaterial);
                renderMaterialGrid();
                flash('素材上传成功');
            } else {
                flash('素材上传失败: ' + result.message);
            }
        } catch (error) {
            console.error('素材上传失败:', error);
            flash('素材上传失败: ' + error.message);
        }
    }


    // ==================== 处理聊天消息 ====================
    function renderChatMessages() {
        const chatSection = document.getElementById('ai-chat-section');
        if (!chatSection) return;

        if (!chatMessages || chatMessages.length === 0) {
            chatSection.innerHTML = `
                <div class="ai-chat-empty">
                    <span class="secondary-text">开始与AI对话吧</span>
                </div>
            `;
            return;
        }

        chatSection.innerHTML = chatMessages.map((msg, index) => {
            if (msg.type === 'user') {
                return `
                    <div class="ai-user-message">
                        <span class="ai-user-message-text">${msg.text || ''}</span>
                        ${msg.attachments ? renderAttachments(msg.attachments) : ''}
                    </div>
                `;
            } else if (msg.type === 'ai') {
                // 确保有文本内容
                const messageText = msg.text || '';
                const streamingDots = msg.isStreaming ?
                    '<span class="streaming-dots"><span>.</span><span>.</span><span>.</span></span>' : '';

                return `
                    <div class="ai-reply-message" data-msg-index="${index}">
                        <div class="ai-reply-content">
                            <div class="ai-reply-card">
                                <div class="ai-reply-text">${messageText}${streamingDots}</div>
                                ${msg.attachments ? renderAttachments(msg.attachments) : ''}
                                <span class="ai-reply-hint">以上内容由AI生成</span>
                            </div>
                            ${msg.isStreaming ? '' : `
                                <div class="ai-message-icons">
                                    <div class="ai-icon-btn" data-action="copy" data-index="${index}">
                                        <img src="/static/project_document/images/icon-copy.svg" />
                                    </div>
                                    <div class="ai-icon-btn" data-action="delete" data-index="${index}">
                                        <img src="/static/project_document/images/icon-trash.svg" />
                                    </div>
                                    <div class="ai-icon-btn ai-icon-edit" data-action="edit" data-index="${index}">
                                        <img src="/static/project_document/images/writing-workspace/icon-edit-dialog.png" />
                                    </div>
                                </div>
                            `}
                        </div>
                    </div>
                `;
            } else if (msg.type === 'loading') {
                return `
                    <div class="ai-reply-message">
                        <div class="ai-reply-content">
                            <div class="ai-reply-card">
                                <div class="ai-reply-text streaming">AI正在思考中...</div>
                                <span class="ai-reply-hint">AI正在生成回复</span>
                            </div>
                        </div>
                    </div>
                `;
            }
            return '';
        }).join('');

        bindChatMessageEvents();

        setTimeout(() => {
            chatSection.scrollTop = chatSection.scrollHeight;
        }, 100);
    }

    function renderAttachments(attachments) {
        if (!attachments || attachments.length === 0) return '';

        return `
            <div class="ai-reply-attachments">
                ${attachments.map(attachment => `
                    <div class="ai-upload-card">
                        <img class="ai-upload-file-icon"
                             src="${attachment.icon || '/static/project_document/images/writing-workspace/icon-file-preview.png'}" />
                        <span class="ai-upload-file-name ml-7">${attachment.name || '附件'}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    function bindChatMessageEvents() {
        const copyBtns = document.querySelectorAll('.ai-icon-btn[data-action="copy"]');
        copyBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.closest('.ai-icon-btn').dataset.index, 10);
                copyMessage(index);
            });
        });

        const deleteBtns = document.querySelectorAll('.ai-icon-btn[data-action="delete"]');
        deleteBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.closest('.ai-icon-btn').dataset.index, 10);
                openDeleteModal({
                    type: 'chat',
                    chatIndex: index,
                    title: '确定删除该对话消息吗？'
                });
            });
        });

        const editBtns = document.querySelectorAll('.ai-icon-btn[data-action="edit"]');
        editBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.closest('.ai-icon-btn').dataset.index, 10);
                openReplyEditModal(index);
            });
        });
    }

    // ==================== AI对话核心业务逻辑 ====================
    function setHistoryOpen(nextState) {
        isHistoryOpen = nextState;
        const aiHistorySection = document.getElementById('ai-history-section');
        const historyDialogBtn = document.getElementById('history-dialog-btn');
        const historyToggle = document.getElementById('toggle-ai-panel');

        if (aiHistorySection) {
            aiHistorySection.classList.toggle('show', isHistoryOpen);
            // 当历史对话区域打开时，加载已删除的改进笔记
            if (isHistoryOpen) {
                loadDeletedImprovementDrafts();
            }
        }
        if (historyDialogBtn) {
            historyDialogBtn.classList.toggle('active', isHistoryOpen);
        }
        if (historyToggle) {
            historyToggle.classList.toggle('active', isHistoryOpen);
        }

        localStorage.setItem('ai_history_open', isHistoryOpen.toString());
    }

    function switchToChatState() {
        const aiPanel = document.getElementById('ai-panel');
        if (aiPanel) {
            aiPanel.classList.add('state-chat');
        }

        // 确保聊天区域可见
        const aiChatSection = document.getElementById('ai-chat-section');
        if (aiChatSection) {
            aiChatSection.style.display = 'block';
        }
    }

    function switchToInitialState() {
        const aiPanel = document.getElementById('ai-panel');
        if (aiPanel) {
            aiPanel.classList.remove('state-chat');
        }
        chatMessages = [];
        currentSessionId = null;
        currentMessageId = null;
        renderChatMessages();
    }

    // 停止所有流式传输
    function stopAllStreaming() {
        if (streamController) {
            streamController.abort();
            streamController = null;
        }

        // 移除所有正在流式传输的标志
        chatMessages.forEach(msg => {
            if (msg.isStreaming) {
                msg.isStreaming = false;
                // 确保文本不为空
                if (!msg.text) {
                    msg.text = '';
                }
            }
        });

        renderChatMessages();
    }

    // ==================== 发送AI消息函数 ====================
    async function sendAiMessage(text) {
        const trimmedText = text.trim();
        const attachments = uploadedFiles.slice(0, 1).map((file) => ({
            name: file.name,
            icon: file.icon,
            isImage: file.isImage,
        }));

        if (!trimmedText && attachments.length === 0) {
            flash('请输入问题或上传文件');
            return;
        }

        // 停止之前的流式传输
        stopAllStreaming();

        // 生成消息ID和会话ID
        const userMessageId = `msg_${Date.now()}_user`;
        if (!currentSessionId) {
            currentSessionId = `session_${Date.now()}`;
        }

        try {
            // 1. 首先调用 add_conversation_message 接口保存用户消息
            const userMessageData = {
                document_id: documentId,
                node_id: currentReviewNodeId,
                session_id: currentSessionId,
                message_id: userMessageId,
                role: 'user',
                content: trimmedText,
                message_type: 'text',
                // 如果有附件，需要处理附件数据
                attachment: uploadedFiles.length > 0 ? {
                    key: uploadedFiles[0].url || uploadedFiles[0].name,
                    name: uploadedFiles[0].name,
                    size: uploadedFiles[0].size || 0,
                    file_url: uploadedFiles[0].url || ''
                } : null
            };

            // 调用添加对话消息接口
            const saveResult = await DataService.addConversationMessage(userMessageData);
            console.log('用户消息保存成功:', saveResult);

            // 更新当前消息ID
            currentMessageId = userMessageId;

            // 2. 添加用户消息到本地聊天记录
            chatMessages.push({
                type: 'user',
                text: trimmedText,
                attachments: attachments.length > 0 ? attachments : undefined,
                id: userMessageId,
                sessionId: currentSessionId
            });

            // 3. 添加AI加载中消息（保存引用）
            const aiMessage = {
                type: 'ai',
                text: '',
                isStreaming: true,
                id: `msg_${Date.now()}_ai`,
                sessionId: currentSessionId
            };
            chatMessages.push(aiMessage);

            // 4. 切换到聊天状态
            switchToChatState();
            renderChatMessages();

            // 5. 构建AI请求的附件数据
            let attachmentData = null;
            if (uploadedFiles.length > 0) {
                const file = uploadedFiles[0];
                attachmentData = {
                    key: file.url || file.name,
                    name: file.name,
                    size: file.size || 0,
                    file_url: file.url || ''
                };
            }

            let aiResult;
            // 判断是否是第一次对话（根据当前是否有会话历史）
            const isFirstMessage = chatMessages.filter(m => m.type === 'user').length <= 1;

            if (isFirstMessage) {
                // 第一次对话，调用 startHelpSession
                aiResult = await DataService.startHelpSession({
                    document_id: documentId,
                    node_id: currentReviewNodeId,
                    help_text: trimmedText,
                    session_id: currentSessionId,
                });
            } else {
                // 多轮对话，调用 sendHelpResponse
                aiResult = await DataService.sendHelpResponse({
                    document_id: documentId,
                    node_id: currentReviewNodeId,
                    session_id: currentSessionId,
                    message: trimmedText,
                    message_id: userMessageId, // 使用用户消息的ID
                    attachment: attachmentData || {}
                });
            }

            // 5.1 清空输入和附件
            const aiInputField = document.getElementById('ai-input-field');
            if (aiInputField) aiInputField.value = '';
            uploadedFiles.length = 0;
            renderUploadedFiles();

            if (aiResult.code !== 200 || !aiResult.data || !aiResult.data.stream) {
                throw new Error(aiResult.message || 'AI请求失败');
            }

            const { stream } = aiResult.data;

            // 6. 处理流式响应（兼容混合格式）
            await stream.process(
                // onChunk 回调：处理数据块
                (chunk) => {
                    // 尝试解析JSON
                    try {
                        const data = JSON.parse(chunk);
                        // 处理会话信息
                        if (data.session_id && data.message_id) {
                            currentSessionId = data.session_id;
                            // 保存message_id到AI消息对象
                            aiMessage.id = data.message_id;
                            return;
                        }
                    } catch (parseError) {
                        // 不是JSON，按文本处理
                    }

                    // 使用保存的引用更新AI消息
                    aiMessage.text += chunk;
                    aiMessage.isStreaming = true;
                    renderChatMessages();
                },
                // onComplete 回调：处理完成
                async (completeData) => {
                    aiMessage.isStreaming = false;

                    // 更新会话ID和消息ID
                    if (completeData.session_id) {
                        currentSessionId = completeData.session_id;
                    }
                    if (completeData.message_id) {
                        currentMessageId = completeData.message_id;
                        aiMessage.id = completeData.message_id;
                    }

                    // 确保AI消息有sessionId
                    aiMessage.sessionId = currentSessionId;

                    // 7. 保存AI回复到数据库- 在 sendHelpResponse 请求中会保存AI回复到数据库

                    renderChatMessages();

                    flash('AI回复完成');
                },
                // onError 回调：错误处理
                (error) => {
                    console.error('AI流式响应错误:', error);

                    // 移除加载中的消息
                    const index = chatMessages.findIndex(msg => msg === aiMessage);
                    if (index !== -1) {
                        chatMessages.splice(index, 1);
                    }
                    renderChatMessages();

                    flash('发送失败: ' + error.message);
                }
            );

        } catch (error) {
            console.error('发送AI消息失败:', error);

            // 移除加载中的消息
            const index = chatMessages.findIndex(msg => msg.isStreaming);
            if (index !== -1) {
                chatMessages.splice(index, 1);
            }
            renderChatMessages();

            flash('发送失败: ' + error.message);
        }
    }

    // ==================== 上传附件卡片渲染函数 ====================

    /**
     * 渲染AI面板上传的文件卡片
     */
    function renderUploadedFiles() {
        const aiInputArea = document.getElementById('ai-input-area');
        const aiUploadTitle = document.getElementById('ai-upload-title');

        if (!aiInputArea) return;

        // 查找或创建上传卡片容器
        let aiUploadCard = document.getElementById('ai-upload-card');
        if (!aiUploadCard) {
            aiUploadCard = document.createElement('div');
            aiUploadCard.id = 'ai-upload-card';
            aiUploadCard.className = 'ai-upload-card';

            // 插入到上传标题下方，输入框上方
            const aiInputRow = aiInputArea.querySelector('.ai-input-row');
            if (aiInputRow) {
                aiInputArea.insertBefore(aiUploadCard, aiInputRow);
            }
        }

        // 如果没有上传文件，隐藏卡片和标题
        if (!uploadedFiles || uploadedFiles.length === 0) {
            aiUploadCard.style.display = 'none';
            if (aiUploadTitle) aiUploadTitle.style.display = 'none';
            return;
        }

        // 显示卡片和标题
        aiUploadCard.style.display = 'inline-flex';
        if (aiUploadTitle) aiUploadTitle.style.display = 'block';

        // 只显示第一个文件
        const file = uploadedFiles[0];
        aiUploadCard.innerHTML = `
            <img class="ai-upload-file-icon" src="${file.icon || '/static/project_document/images/writing-workspace/icon-file-preview.png'}" />
            <span class="ai-upload-file-name ml-7">${file.name}</span>
            <img class="ai-upload-remove ml-7" src="/static/project_document/images/writing-workspace/icon-delete-file.png" />
        `;

        // 绑定删除按钮事件
        const removeBtn = aiUploadCard.querySelector('.ai-upload-remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                uploadedFiles = [];
                renderUploadedFiles();
                flash('附件已移除');
            });
        }

        // 更新发送按钮状态
        updateAiPanelSendButton();
    }

    /**
     * 渲染AI对话弹窗上传的文件卡片
     */
    function renderDialogUploadedFiles() {
        const aiDialogInputArea = document.querySelector('.ai-dialog-input-area');
        const aiDialogUploadTitle = document.getElementById('ai-dialog-upload-title');

        if (!aiDialogInputArea) return;

        // 查找或创建上传卡片容器
        let aiDialogUploadCard = document.getElementById('ai-dialog-upload-card');
        if (!aiDialogUploadCard) {
            aiDialogUploadCard = document.createElement('div');
            aiDialogUploadCard.id = 'ai-dialog-upload-card';
            aiDialogUploadCard.className = 'ai-upload-card';

            // 插入到上传标题下方，输入框上方
            const aiDialogUploadBlock = document.getElementById('ai-dialog-upload-block');
            if (aiDialogUploadBlock) {
                const aiDialogInputRow = aiDialogUploadBlock.querySelector('.ai-dialog-input-row');
                if (aiDialogInputRow) {
                    aiDialogUploadBlock.insertBefore(aiDialogUploadCard, aiDialogInputRow);
                } else {
                    aiDialogUploadBlock.appendChild(aiDialogUploadCard);
                }
            }
        }

        // 如果没有上传文件，隐藏卡片和标题
        if (!dialogUploadedFiles || dialogUploadedFiles.length === 0) {
            aiDialogUploadCard.style.display = 'none';
            if (aiDialogUploadTitle) aiDialogUploadTitle.style.display = 'none';
            return;
        }

        // 显示卡片和标题
        aiDialogUploadCard.style.display = 'inline-flex';
        if (aiDialogUploadTitle) aiDialogUploadTitle.style.display = 'block';

        // 只显示第一个文件
        const file = dialogUploadedFiles[0];
        aiDialogUploadCard.innerHTML = `
            <img class="ai-upload-file-icon" src="${file.icon || '/static/project_document/images/writing-workspace/icon-file-preview.png'}" />
            <span class="ai-upload-file-name ml-7">${file.name}</span>
            <img class="ai-upload-remove ml-7" src="/static/project_document/images/writing-workspace/icon-delete-file.png" />
        `;

        // 绑定删除按钮事件
        const removeBtn = aiDialogUploadCard.querySelector('.ai-upload-remove');
        if (removeBtn) {
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                dialogUploadedFiles = [];
                renderDialogUploadedFiles();
                flash('附件已移除');
                // 更新发送按钮状态
                updateHeuristicDialogSendButton();
            });
        }

        // 更新发送按钮状态
        updateHeuristicDialogSendButton();
    }

    /**
     * 更新AI面板发送按钮状态
     */
    function updateAiPanelSendButton() {
        const aiInputField = document.getElementById('ai-input-field');
        const aiSendBtn = document.getElementById('ai-send-btn');

        if (aiInputField && aiSendBtn) {
            const hasText = aiInputField.value.trim().length > 0;
            const hasFile = uploadedFiles.length > 0;

            if (hasText || hasFile) {
                aiSendBtn.classList.add('active');
                aiSendBtn.style.cursor = 'pointer';
            } else {
                aiSendBtn.classList.remove('active');
                aiSendBtn.style.cursor = 'not-allowed';
            }
        }
    }

    /**
     * 更新AI对话弹窗发送按钮状态
     */
    function updateHeuristicDialogSendButton() {
        const aiDialogInput = document.getElementById('ai-dialog-input');
        const aiDialogSend = document.getElementById('ai-dialog-send');

        if (aiDialogInput && aiDialogSend) {
            const hasText = aiDialogInput.value.trim().length > 0;
            const hasFile = dialogUploadedFiles.length > 0;

            if (hasText || hasFile) {
                aiDialogSend.classList.add('active');
                aiDialogSend.style.cursor = 'pointer';
                aiDialogSend.style.opacity = '1';
            } else {
                aiDialogSend.classList.remove('active');
                aiDialogSend.style.cursor = 'not-allowed';
                aiDialogSend.style.opacity = '0.5';
            }
        }
    }

    // ==================== 图片大小检查函数 ====================
    /**
     * 检查图片文件大小是否超过5MB
     * @param {File} file - 要检查的文件
     * @param {boolean} isImage - 是否为图片文件
     * @returns {boolean} - 是否通过检查
     */
    function checkImageFileSize(file, isImage) {
        if (!isImage) return true; // 非图片文件不检查大小

        const maxSize = MAX_IMAGE_SIZE; // 5MB
        if (file.size > maxSize) {
            flash('图片大小不能超过5MB');
            return false;
        }
        return true;
    }

    /**
     * 处理AI面板文件上传
     */
    async function handleAiAttachmentUpload(file, isImage) {
        // 检查图片大小
        if (isImage && !checkImageFileSize(file, isImage)) {
            return null;
        }

        try {
            let result;
            if (isImage) {
                result = await DataService.uploadImg(file);
            } else {
                result = await DataService.uploadFile(file);
            }

            if (result.code === 200 || result.code === 1) {
                const attachment = {
                    name: file.name,
                    url: result.data?.url || result.url,
                    size: file.size,
                    type: file.type,
                    icon: isImage ?
                        '/static/project_document/images/writing-workspace/icon-file-preview.png' :
                        '/static/project_document/images/writing-workspace/icon-uploaded-file.svg',
                    isImage: isImage
                };

                uploadedFiles = [attachment]; // 只保留一个文件
                renderUploadedFiles(); // 渲染上传卡片

                flash('文件上传成功');
                return attachment;
            } else {
                flash('文件上传失败: ' + (result.message || result.msg));
                return null;
            }
        } catch (error) {
            console.error('文件上传失败:', error);
            flash('文件上传失败: ' + error.message);
            return null;
        }
    }

    /**
     * 处理对话弹窗文件上传
     */
    async function handleDialogAttachmentUpload(file, isImage) {
        // 检查图片大小
        if (isImage && !checkImageFileSize(file, isImage)) {
            return null;
        }

        try {
            let result;
            if (isImage) {
                result = await DataService.uploadImg(file);
            } else {
                result = await DataService.uploadFile(file);
            }

            if (result.code === 200 || result.code === 1) {
                const attachment = {
                    name: file.name,
                    url: result.data?.url || result.url,
                    size: file.size,
                    type: file.type,
                    icon: isImage ?
                        '/static/project_document/images/writing-workspace/icon-file-preview.png' :
                        '/static/project_document/images/writing-workspace/icon-uploaded-file.svg',
                    isImage: isImage
                };

                dialogUploadedFiles = [attachment]; // 只保留一个文件
                renderDialogUploadedFiles(); // 渲染上传卡片

                flash('文件上传成功');
                // 更新发送按钮状态
                updateHeuristicDialogSendButton();
                return attachment;
            } else {
                flash('文件上传失败: ' + (result.message || result.msg));
                return null;
            }
        } catch (error) {
            console.error('文件上传失败:', error);
            flash('文件上传失败: ' + error.message);
            return null;
        }
    }

    // ==================== AI启发式写作对话框函数 ====================
    async function openHeuristicWritingDialog() {
        // 保存当前章节内容
        const saved = await saveCurrentSection();
        if (!saved) {
            flash('保存当前章节失败，请稍后重试');
            return;
        }

        const aiDialogOverlay = document.getElementById('ai-dialog-modal-overlay');
        const aiDialogContent = document.getElementById('ai-dialog-content');
        const aiDialogInput = document.getElementById('ai-dialog-input');
        const aiDialogSend = document.getElementById('ai-dialog-send');

        if (!aiDialogOverlay || !aiDialogContent) {
            flash('对话框元素未找到');
            return;
        }

        // 重置对话框状态
        heuristicDialogMessages = [];
        heuristicCurrentRound = 0;
        dialogUploadedFiles = []; // 清空上传文件

        // 清空内容
        aiDialogContent.innerHTML = '';
        aiDialogInput.value = '';

        // 清除上传文件显示
        renderDialogUploadedFiles();

        // 显示对话框
        aiDialogOverlay.classList.add('show');

        // 禁用输入框和发送按钮
        if (aiDialogInput) aiDialogInput.disabled = true;
        if (aiDialogSend) aiDialogSend.style.opacity = '0.5';
        aiDialogSend.style.cursor = 'not-allowed';

        // 添加加载中消息
        addHeuristicLoadingMessage();

        // 开始启发式写作
        startHeuristicWriting();
    }

    function addHeuristicLoadingMessage() {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (!aiDialogContent) return;

        // 清除之前的加载中消息
        removeHeuristicLoadingMessage();

        // 创建加载中消息元素
        const loadingMsg = document.createElement('div');
        loadingMsg.className = 'ai-dialog-message-ai';
        loadingMsg.id = 'ai-dialog-loading-message';

        // 计时器状态
        let seconds = 0;

        // 更新计时器显示的函数
        function updateTimerDisplay() {
            const formattedTime = seconds.toString().padStart(2, '0');
            const textElement = loadingMsg.querySelector('.ai-dialog-timer-text');
            let lastMessage = ''
            if (heuristicCurrentRound >= 5){
                lastMessage = '感谢您的回答，我将根据您提供的信息进行文章初始化/优化，请等待（预计需要1~3分钟）。'
            }
            if (textElement) {
                textElement.textContent = `${lastMessage} AI正在思考中... ${formattedTime}秒`;
            }
        }

        loadingMsg.innerHTML = `
            <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
            <div class="ai-dialog-message-content">
                <div class="ai-dialog-bubble-ai">
                    <span class="ai-dialog-text ai-dialog-timer-text">AI正在思考中... 00秒</span>
                </div>
            </div>
        `;

        aiDialogContent.appendChild(loadingMsg);
        scrollHeuristicDialogToBottom();

        // 启动计时器
        const timerInterval = setInterval(() => {
            seconds++;
            updateTimerDisplay();

            // 保存计时器ID到消息元素上，以便后续清除
            loadingMsg.dataset.timerId = timerInterval;
        }, 1000);

        // 保存计时器ID到消息元素上
        loadingMsg.dataset.timerId = timerInterval;
    }

    function removeHeuristicLoadingMessage() {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (!aiDialogContent) return;

        // 查找加载中消息
        const loadingMsg = aiDialogContent.querySelector('#ai-dialog-loading-message');
        if (loadingMsg) {
            // 清除计时器
            const timerId = loadingMsg.dataset.timerId;
            if (timerId) {
                clearInterval(parseInt(timerId));
            }

            // 移除消息元素
            loadingMsg.remove();
        }
    }

    function addHeuristicAIMessage(content) {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (!aiDialogContent) return;

        // 移除加载中消息
        removeHeuristicLoadingMessage();

        const messageDiv = document.createElement('div');
        messageDiv.className = 'ai-dialog-message-ai';
        messageDiv.innerHTML = `
            <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
            <div class="ai-dialog-message-content">
                <div class="ai-dialog-bubble-ai">
                    <span class="ai-dialog-text">${content}</span>
                    <span class="ai-dialog-hint">以上内容由AI生成</span>
                </div>
            </div>
        `;
        aiDialogContent.appendChild(messageDiv);
        scrollHeuristicDialogToBottom();

        // 保存到消息历史
        heuristicDialogMessages.push({
            type: 'ai',
            content: content,
            timestamp: Date.now()
        });

        // 如果是第5轮或者状态为draft，自动保存到编辑器
        if (heuristicCurrentRound >= 5 || content.includes('这是根据对话生成的正文内容')) {
            setTimeout(() => {
                console.log('5轮对话结束')
            }, 1000);
        }
    }

    function addHeuristicUserMessage(content) {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (!aiDialogContent) return;

        const messageDiv = document.createElement('div');
        messageDiv.className = 'ai-dialog-message-user';
        messageDiv.innerHTML = `
            <div class="ai-dialog-bubble-user">
                <span class="ai-dialog-text">${content}</span>
            </div>
            <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-assistant.png" />
        `;
        aiDialogContent.appendChild(messageDiv);
        scrollHeuristicDialogToBottom();

        // 保存到消息历史
        heuristicDialogMessages.push({
            type: 'user',
            content: content,
            timestamp: Date.now()
        });

        heuristicCurrentRound++;
    }

    function scrollHeuristicDialogToBottom() {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (aiDialogContent) {
            setTimeout(() => {
                aiDialogContent.scrollTop = aiDialogContent.scrollHeight;
            }, 100);
        }
    }

    async function startHeuristicWriting() {
        try {
            // 生成会话ID
            const sessionId = `heuristic_${Date.now()}`;
            heuristicSessionId = sessionId;

            // 调用启发式写作接口
            const result = await DataService.startHeuristicWriting({
                document_id: documentId,
                node_id: currentSectionNodeId,
                session_id: sessionId,
                text: '开始启发式写作'
            });

            if (result.code !== 200 || !result.data || !result.data.stream) {
                throw new Error(result.message || '启发式写作请求失败');
            }

            const { stream } = result.data;
            heuristicStreamHandler = stream;

            // 启用输入框和发送按钮（但根据内容状态更新）
            const aiDialogInput = document.getElementById('ai-dialog-input');
            const aiDialogSend = document.getElementById('ai-dialog-send');
            if (aiDialogInput) {
                aiDialogInput.disabled = false;
                // 监听输入事件，更新发送按钮状态
                aiDialogInput.addEventListener('input', updateHeuristicDialogSendButton);
            }
            // 发送按钮状态会在 updateHeuristicDialogSendButton 中更新

            // 处理流式响应
            let aiResponse = '';
            await stream.process(
                // onChunk回调：处理数据块
                (chunk) => {
                    // 尝试解析JSON
                    try {
                        const data = JSON.parse(chunk);
                        // 处理会话信息
                        if (data.session_id && data.message_id) {
                            heuristicSessionId = data.session_id;
                            heuristicMessageId = data.message_id;
                            return;
                        }
                    } catch (parseError) {
                        // 不是JSON，按文本处理
                    }

                    // 更新AI响应内容
                    aiResponse += chunk;

                    // 移除加载中消息，添加AI消息
                    removeHeuristicLoadingMessage();
                    const aiDialogContent = document.getElementById('ai-dialog-content');
                    if (aiDialogContent) {
                        let aiMessageDiv = aiDialogContent.querySelector('.ai-dialog-message-ai:last-child');
                        if (!aiMessageDiv) {
                            addHeuristicAIMessage(aiResponse);
                        } else {
                            const textSpan = aiMessageDiv.querySelector('.ai-dialog-text');
                            if (textSpan) {
                                textSpan.textContent = aiResponse;
                            }
                        }
                    }
                },
                // onComplete回调：处理完成
                (completeData) => {
                    console.log('启发式写作完成:', completeData);

                    // 更新会话ID和消息ID
                    if (completeData.session_id) {
                        heuristicSessionId = completeData.session_id;
                    }
                    if (completeData.message_id) {
                        heuristicMessageId = completeData.message_id;
                    }

                    // 保存到消息历史
                    heuristicDialogMessages.push({
                        type: 'ai',
                        content: completeData.full_message || aiResponse,
                        timestamp: Date.now()
                    });

                    flash('AI提问已完成，请回答');
                },
                // onError回调：错误处理
                (error) => {
                    console.error('启发式写作流式响应错误:', error);

                    // 移除加载中消息
                    removeHeuristicLoadingMessage();

                    // 显示错误消息
                    const aiDialogContent = document.getElementById('ai-dialog-content');
                    if (aiDialogContent) {
                        const errorMsg = document.createElement('div');
                        errorMsg.className = 'ai-dialog-message-ai';
                        errorMsg.innerHTML = `
                            <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                            <div class="ai-dialog-message-content">
                                <div class="ai-dialog-bubble-ai" style="background-color: #fff0f0;">
                                    <span class="ai-dialog-text">抱歉，AI服务暂时不可用。请稍后重试。</span>
                                </div>
                            </div>
                        `;
                        aiDialogContent.appendChild(errorMsg);
                    }

                    flash('启发式写作失败: ' + error.message);
                }
            );

        } catch (error) {
            console.error('启发式写作失败:', error);

            // 移除加载中消息
            removeHeuristicLoadingMessage();

            // 显示错误消息
            const aiDialogContent = document.getElementById('ai-dialog-content');
            if (aiDialogContent) {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'ai-dialog-message-ai';
                errorMsg.innerHTML = `
                    <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                    <div class="ai-dialog-message-content">
                        <div class="ai-dialog-bubble-ai" style="background-color: #fff0f0;">
                            <span class="ai-dialog-text">抱歉，启动启发式写作失败。</span>
                        </div>
                    </div>
                `;
                aiDialogContent.appendChild(errorMsg);
            }

            flash('启发式写作失败: ' + error.message);
        }
    }

    async function sendHeuristicResponse() {
        const aiDialogInput = document.getElementById('ai-dialog-input');
        if (!aiDialogInput) return;

        const userInput = aiDialogInput.value.trim();

        // 检查是否有输入内容或上传文件
        if (!userInput && dialogUploadedFiles.length === 0) {
            flash('请输入回答内容或上传文件');
            return;
        }

        if (!heuristicSessionId || !heuristicMessageId) {
            flash('会话信息不完整，请重新开始');
            return;
        }

        // 保存附件数据，因为后面会清空
        const attachments = [...dialogUploadedFiles];

        // 添加用户消息
        addHeuristicUserMessage(userInput || `已上传文件: ${attachments[0]?.name}`);

        // 清空输入框
        aiDialogInput.value = '';

        // 禁用输入框和发送按钮
        aiDialogInput.disabled = true;
        const aiDialogSend = document.getElementById('ai-dialog-send');
        if (aiDialogSend) {
            aiDialogSend.style.opacity = '0.5';
            aiDialogSend.style.cursor = 'not-allowed';
        }

        // 添加加载中消息
        addHeuristicLoadingMessage();

        try {
            // 获取附件
            const attachment = attachments.length > 0 ? {
                key: attachments[0].url || attachments[0].name,
                name: attachments[0].name,
                size: attachments[0].size || 0,
                file_url: attachments[0].url || ''
            } : {};

            // 构建请求参数
            const requestParams = {
                document_id: documentId,
                node_id: currentSectionNodeId,
                session_id: heuristicSessionId,
                messages: userInput || '',  // 注意：后端接口期望的是messages字段
                message_id: heuristicMessageId,
                attachment: attachment
            };

            console.log('发送启发式回复请求参数:', requestParams);

            // 调用启发式写作回复接口
            const result = await DataService.sendHeuristicResponse(requestParams);

            if (result.code !== 200 || !result.data || !result.data.stream) {
                throw new Error(result.message || '发送回复失败');
            }

            const { stream } = result.data;
            heuristicStreamHandler = stream;

            // 处理流式响应
            let aiResponse = '';
            let status = 'ask';
            let accumulatedText = '';

            await stream.process(
                // onChunk回调：处理数据块
                (chunk) => {

                    // 尝试解析JSON
                    try {
                        const data = JSON.parse(chunk);

                        // 处理会话信息
                        if (data.session_id && data.message_id) {
                            heuristicSessionId = data.session_id;
                            heuristicMessageId = data.message_id;
                            return;
                        }

                        // 处理状态信息
                        if (data.status) {
                            status = data.status;
                            console.log('状态更新:', status);
                            return;
                        }

                        // 处理assistantMessage
                        if (data.assistantMessage && data.assistantMessage.messageId) {
                            heuristicMessageId = data.assistantMessage.messageId;
                            return;
                        }

                        // 处理done信号
                        if (data.done) {
                            console.log('收到完成信号:', data);
                            return;
                        }

                        // 处理delta字段 - 直接添加到响应中
                        if (data.delta) {
                            accumulatedText += data.delta;
                            aiResponse += data.delta;
                            updateHeuristicAIMessage(accumulatedText);
                            return;
                        }

                        // 如果没有delta字段但有content字段
                        if (data.content) {
                            accumulatedText += data.content;
                            aiResponse += data.content;
                            updateHeuristicAIMessage(accumulatedText);
                            return;
                        }

                        // 如果是其他格式的JSON，转换为字符串处理
                        const jsonStr = JSON.stringify(data);
                        accumulatedText += jsonStr;
                        aiResponse += jsonStr;
                        updateHeuristicAIMessage(accumulatedText);

                    } catch (parseError) {
                        // 不是JSON，按文本处理
                        accumulatedText += chunk;
                        aiResponse += chunk;
                        if (heuristicCurrentRound < 5){  // 最后一轮的正文无需显示
                            updateHeuristicAIMessage(accumulatedText);
                        }
                    }
                },
                // onComplete回调：处理完成
                (completeData) => {
                    console.log('启发式回复完成:', completeData);
                    // 使用 completeData.status 而不是之前的 status 变量
                    const finalStatus = completeData.status || status; // 优先使用 completeData.status

                    // 确保所有文本都已显示
                    if (accumulatedText && accumulatedText !== aiResponse && finalStatus!='draft') {
                        updateHeuristicAIMessage(accumulatedText);
                    }

                    // 移除加载中消息
                    if (heuristicCurrentRound < 5){  // 最后一轮的计时消息无需移除
                        removeHeuristicLoadingMessage();
                    }
                    // 启用输入框和发送按钮
                    aiDialogInput.disabled = false;
                    if (aiDialogSend) aiDialogSend.style.opacity = '1';

                    // 保存到消息历史
                    if (accumulatedText) {
                        heuristicDialogMessages.push({
                            type: 'ai',
                            content: accumulatedText,
                            timestamp: Date.now()
                        });
                    }

                    // 如果状态为draft，显示提示
                    if (finalStatus === 'draft') {
                        flash('启发式写作完成，内容已保存到编辑器');
                        setTimeout(() => {
                            if (completeData.full_message){
                                DataService.navigateToPage(`/project_document/full-compare/${documentId}`, { document_id: documentId, node_id: currentSectionNodeId, full_text:completeData.full_message,source: 'heuristic'});
                            }
                            else{
                                DataService.navigateToPage(`/project_document/full-compare/${documentId}`, { document_id: documentId, node_id: currentSectionNodeId, full_text:accumulatedText,source: 'heuristic'});
                            }
                            closeHeuristicDialog();
                        }, 1000);
                    } else {
                        flash('请继续回答AI的问题');
                    }

                    // 清空附件
                    dialogUploadedFiles = [];
                    renderDialogUploadedFiles();
                },
                // onError回调：错误处理
                (error) => {
                    console.error('启发式回复流式响应错误:', error);

                    // 移除加载中消息
                    removeHeuristicLoadingMessage();

                    // 启用输入框和发送按钮
                    aiDialogInput.disabled = false;
                    if (aiDialogSend) aiDialogSend.style.opacity = '1';

                    // 显示错误消息
                    const aiDialogContent = document.getElementById('ai-dialog-content');
                    if (aiDialogContent) {
                        const errorMsg = document.createElement('div');
                        errorMsg.className = 'ai-dialog-message-ai';
                        errorMsg.innerHTML = `
                            <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                            <div class="ai-dialog-message-content">
                                <div class="ai-dialog-bubble-ai" style="background-color: #fff0f0;">
                                    <span class="ai-dialog-text">抱歉，发送回复失败。</span>
                                </div>
                            </div>
                        `;
                        aiDialogContent.appendChild(errorMsg);
                    }

                    flash('发送回复失败: ' + error.message);
                }
            );

        } catch (error) {
            console.error('发送启发式回复失败:', error);

            // 移除加载中消息
            removeHeuristicLoadingMessage();

            // 启用输入框和发送按钮
            aiDialogInput.disabled = false;
            if (aiDialogSend) aiDialogSend.style.opacity = '1';

            // 清空附件
            dialogUploadedFiles = [];
            renderDialogUploadedFiles();

            flash('发送回复失败: ' + error.message);
        }
    }

    function updateHeuristicAIMessage(content) {
        const aiDialogContent = document.getElementById('ai-dialog-content');
        if (!aiDialogContent) return;

        // 移除加载中消息
        removeHeuristicLoadingMessage();

        // 查找或创建AI消息元素
        let aiMessageDiv = aiDialogContent.querySelector('.ai-dialog-message-ai:last-child');
        if (!aiMessageDiv) {
            // 创建新的AI消息
            aiMessageDiv = document.createElement('div');
            aiMessageDiv.className = 'ai-dialog-message-ai';
            aiMessageDiv.innerHTML = `
                <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                <div class="ai-dialog-message-content">
                    <div class="ai-dialog-bubble-ai">
                        <span class="ai-dialog-text"></span>
                        <span class="ai-dialog-hint">以上内容由AI生成</span>
                    </div>
                </div>
            `;
            aiDialogContent.appendChild(aiMessageDiv);
        }

        // 更新文本内容
        const textSpan = aiMessageDiv.querySelector('.ai-dialog-text');
        if (textSpan) {
            textSpan.textContent = content;
        }

        scrollHeuristicDialogToBottom();
    }

    function closeHeuristicDialog() {
        const aiDialogOverlay = document.getElementById('ai-dialog-modal-overlay');
        if (aiDialogOverlay) {
            aiDialogOverlay.classList.remove('show');
        }

        // 停止流式传输
        if (heuristicStreamHandler) {
            heuristicStreamHandler.cancel();
            heuristicStreamHandler = null;
        }

        // 重置状态
        heuristicSessionId = null;
        heuristicMessageId = null;
        heuristicDialogMessages = [];
        heuristicCurrentRound = 0;
        dialogUploadedFiles = [];
    }

    // ==================== 事件绑定函数 ====================
    function bindEvents() {
        bindHeaderEvents();
        bindOutlinePanelEvents();
        bindEditorEvents();
        bindReviewPanelEvents();
        bindNotesPanelEvents();
        bindAiPanelEvents();
        bindModalEvents();
        bindSelectionToolbarEvents();
        bindResizeEvents();
        bindHeuristicDialogEvents(); // 新增：绑定启发式写作对话框事件
        bindFullTextReviewEvents();
    }

    function bindFullTextReviewEvents(){
        const btn = document.getElementById('btn-full-text-review');
        btn.addEventListener('click', () => {
                const modal = document.getElementById('regenerate-confirm-overlay-full-text');
                const title = document.getElementById('regenerate-confirm-modal-title');
                const waitingArea = document.getElementById('waitingArea');
                if (modal && title && waitingArea) {
                  // 重置弹窗状态
                  title.textContent = '将对全文进行AI评审，是否继续？';
                  waitingArea.style.display = 'none';
                  modal.classList.add('show');
                  // 重置按钮状态
                  const cancelBtn = document.getElementById('regenerate-confirm-cancel-full-text');
                  const continueBtn = document.getElementById('regenerate-confirm-continue-full-text');
                  if (cancelBtn && continueBtn) {
                    // 移除之前的事件监听器（通过克隆替换）
                    // 绑定新的事件
                    cancelBtn.addEventListener('click',()=>{
                            closeConfirmMergeModal();
                            flash('已取消全文评审');
                    });
                    continueBtn.addEventListener('click',()=>{
                    });
                  }
                  // 绑定遮罩层点击事件
                  modal.removeEventListener('click', handleModalClick);
                  modal.addEventListener('click', handleModalClick);
                }
        })
    }

    function bindHeuristicDialogEvents() {
        const aiDialogOverlay = document.getElementById('ai-dialog-modal-overlay');
        const aiDialogClose = document.getElementById('ai-dialog-close');
        const aiDialogContent = document.getElementById('ai-dialog-content');
        const aiDialogInput = document.getElementById('ai-dialog-input');
        const aiDialogSend = document.getElementById('ai-dialog-send');
        const dialogUploadFileTrigger = document.getElementById('ai-dialog-upload-file-trigger');
        const dialogUploadFileInput = document.getElementById('ai-dialog-upload-file-input');
        const dialogUploadImageTrigger = document.getElementById('ai-dialog-upload-image-trigger');
        const dialogUploadImageInput = document.getElementById('ai-dialog-upload-image-input');

        // 关闭按钮
        if (aiDialogClose) {
            aiDialogClose.addEventListener('click', closeHeuristicDialog);
        }

        // 发送按钮
        if (aiDialogSend) {
            aiDialogSend.addEventListener('click', sendHeuristicResponse);
        }

        // 输入框回车发送
        if (aiDialogInput) {
            aiDialogInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendHeuristicResponse();
                }
            });

            // 输入框输入时更新发送按钮状态
            aiDialogInput.addEventListener('input', updateHeuristicDialogSendButton);
        }

        // 文件上传
        if (dialogUploadFileTrigger && dialogUploadFileInput) {
            dialogUploadFileTrigger.addEventListener('click', () => dialogUploadFileInput.click());
            dialogUploadFileInput.addEventListener('change', async (e) => {
                const file = e.target.files && e.target.files[0];
                if (file) {
                    await handleDialogAttachmentUpload(file, false);
                    dialogUploadFileInput.value = '';
                }
            });
        }

        // 图片上传
        if (dialogUploadImageTrigger && dialogUploadImageInput) {
            dialogUploadImageTrigger.addEventListener('click', () => dialogUploadImageInput.click());
            dialogUploadImageInput.addEventListener('change', async (e) => {
                const file = e.target.files && e.target.files[0];
                if (file) {
                    await handleDialogAttachmentUpload(file, true);
                    dialogUploadImageInput.value = '';
                }
            });
        }
    }

    function bindHeaderEvents() {
        const backLink = document.querySelector('.header-left-pos');
        if (backLink) {
            backLink.addEventListener('click', async (e) => {
                e.preventDefault();
                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    document.getElementById('exit-modal-overlay').classList.add('show');
                } else {
                    flash('保存失败，请稍后重试');
                }
            });
        }

        const buttons = document.querySelectorAll('.header-right-pos .header-btn, .header-right-pos .header-btn-primary');
        buttons.forEach(btn => {
            btn.addEventListener('click', async () => {
                const text = btn.innerText.trim();

                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (!saved && text !== '存档') {
                    flash('保存当前章节失败，操作已取消');
                    return;
                }

                if (text === '存档') {
                    // 存档按钮已经在点击时保存了
                    flash('小节内容已保存');
                } else if (text === '全文预览') {
                    window.location.href = `/project_document/preview-review/${documentId}?mode=editable`;
                }  else if (text === '写作指导') {
                    window.location.href = `/project_document/outline-confirm/${documentId}`;
                } else {
                    flash(text + ' 功能占位');
                }
            });
        });
    }

    function bindOutlinePanelEvents() {
        const outlineTab = document.querySelector('.outline-title-pos');
        const chapterPointsTab = document.querySelector('.chapter-points-title-pos');

        if (outlineTab && chapterPointsTab) {
            outlineTab.addEventListener('click', () => setActiveTab('outline'));
            chapterPointsTab.addEventListener('click', () => setActiveTab('chapter-points'));
        }

        const collapseOutlineBtn = document.getElementById('collapse-icon');
        const outlineCollapsedBar = document.getElementById('outline-panel-collapsed-bar');

        if (collapseOutlineBtn && outlineCollapsedBar) {
            collapseOutlineBtn.addEventListener('click', () => {
                document.querySelector('.outline-panel').classList.add('collapsed');
                outlineCollapsedBar.classList.add('show');
            });

            outlineCollapsedBar.addEventListener('click', () => {
                document.querySelector('.outline-panel').classList.remove('collapsed');
                outlineCollapsedBar.classList.remove('show');
            });
        }
    }

    function setActiveTab(tabName) {
        const outlinePane = document.getElementById('outline-content');
        const chapterPane = document.getElementById('chapter-points-content');
        const outlineTab = document.querySelector('.outline-title-pos');
        const chapterPointsTab = document.querySelector('.chapter-points-title-pos');
        const tabUnderline = document.querySelector('.tab-underline');

        if (tabName === 'outline') {
            outlinePane.style.display = 'flex';
            chapterPane.style.display = 'none';
            outlineTab.style.color = '#217efd';
            chapterPointsTab.style.color = '#557496';

            // 移动横线到"全文大纲"下方
            if (tabUnderline) {
                tabUnderline.classList.remove('tab-underline-chapter');
                tabUnderline.classList.add('tab-underline-outline');
            }

            activeTab = 'outline';
        } else {
            outlinePane.style.display = 'none';
            chapterPane.style.display = 'flex';
            outlineTab.style.color = '#557496';
            chapterPointsTab.style.color = '#217efd';

            // 移动横线到"章节要点"下方
            if (tabUnderline) {
                tabUnderline.classList.remove('tab-underline-outline');
                tabUnderline.classList.add('tab-underline-chapter');
            }

            // 切换到章节要点标签时，渲染章节要点内容
            renderChapterPoints();
            activeTab = 'chapter-points';
        }
    }

    function bindEditorEvents() {
        // 修改：将AI启发式写作按钮绑定到新的函数
        const aiWritingBtn = document.querySelector('.ai-writing-btn');
        if (aiWritingBtn) {
            aiWritingBtn.addEventListener('click', () => {
                openHeuristicWritingDialog();  // AI启发式写作（内部已保存）
            });
        }

        // 评审本节 - 修改：添加按钮状态检查
        const reviewSectionBtn = document.querySelector('.review-section-btn');
        if (reviewSectionBtn) {
            reviewSectionBtn.addEventListener('click', async () => {
                // 检查按钮是否被禁用
                if (reviewSectionBtn.classList.contains('disabled')) {
                    flash('内容未修改，无需重新评审');
                    return;
                }

                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    // 设置合并按钮为小节模式
                    setMergeButtonType('section');
                    startSectionReview(currentSectionNodeId);
                    // 禁用按钮
                    const reviewSectionBtn = document.querySelector('.review-section-btn');
                    if (reviewSectionBtn) {
                       disableReviewButton(reviewSectionBtn);
                    }
                } else {
                    flash('保存当前章节失败，请稍后重试');
                }
            });
        }

        // 评审本章 - 修改：添加按钮状态检查
        const reviewChapterBtn = document.querySelector('.review-chapter-text-pos');
        if (reviewChapterBtn) {
            reviewChapterBtn.addEventListener('click', async () => {
                // 注意：评审本章不需要检查按钮状态，因为它评审的是整个章节
                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    // 设置合并按钮为章节模式
                    setMergeButtonType('chapter');
                    startSectionReview(currentSectionNodeId.split(".")[0]);
                } else {
                    flash('保存当前章节失败，请稍后重试');
                }
            });
        }

        const floatBallToggle = document.getElementById('toggle-float-ball');
        if (floatBallToggle) {
            floatBallToggle.addEventListener('click', () => {
                floatBallToggle.classList.toggle('active');
            });
        }
    }

    function bindReviewPanelEvents() {
        const collapseReviewBtn = document.getElementById('collapse-review-panel');
        const reviewPanelBar = document.getElementById('review-panel-collapsed-bar');

        if (collapseReviewBtn && reviewPanelBar) {
            collapseReviewBtn.addEventListener('click', () => {
                document.querySelector('.review-section').classList.add('collapsed');
                reviewPanelBar.classList.add('show');
            });

            reviewPanelBar.addEventListener('click', () => {
                document.querySelector('.review-section').classList.remove('collapsed');
                reviewPanelBar.classList.remove('show');
            });
        }

        // 获取评审范围切换按钮
        const thisSectionBtn = document.getElementById('thisSection');
        const thisChapterBtn = document.getElementById('thisChapter');

        if (thisSectionBtn && thisChapterBtn) {
            // 初始化按钮状态
            updateReviewScopeButtons();

            // 本节按钮点击事件
            thisSectionBtn.addEventListener('click', async () => {
                if (currentReviewScope === 'section') return;

                currentReviewScope = 'section';
                currentReviewNodeId = currentSectionNodeId;

                // 更新按钮状态
                updateReviewScopeButtons();

                // 加载本节评审数据
                await loadReviewData(currentReviewNodeId);

                // 加载本节改进笔记
                await loadImprovementDrafts();

                // 更新合并按钮
                updateMergeButton();

                flash('已切换到本节评审');
            });

            // 本章按钮点击事件
            thisChapterBtn.addEventListener('click', async () => {
                if (currentReviewScope === 'chapter') return;

                currentReviewScope = 'chapter';

                // 根据当前节点级别确定章节节点ID
                if (currentSectionLevel === 1) {
                    // 当前节点本身就是章节
                    currentReviewNodeId = currentSectionNodeId;
                } else {
                    // 当前节点是小节，获取对应的章节节点ID
                    currentReviewNodeId = currentSectionNodeId.split('.')[0];
                }

                // 更新按钮状态
                updateReviewScopeButtons();

                // 加载本章评审数据
                await loadReviewData(currentReviewNodeId);

                // 加载本章改进笔记
                await loadImprovementDrafts();

                // 更新合并按钮
                updateMergeButton();

                flash('已切换到本章评审');
            });
        }

        // 修改：点击详情按钮时显示当前评审内容
        const reviewDetailBtn = document.querySelector('.review-detail-text-pos');
        if (reviewDetailBtn) {
            reviewDetailBtn.addEventListener('click', () => {
                // 获取review-score中的内容
                const reviewScore = document.getElementById('review-score');
                const reviewDetailScoreText = document.getElementById('review-detail-score-text');
                if (reviewScore && reviewDetailScoreText) {
                    // 将review-score的内容复制到review-detail-score-text中
                    reviewDetailScoreText.innerHTML = reviewScore.innerHTML+``;
                }
                // 获取review-content中的内容
                const reviewContent = document.getElementById('review-content');
                const reviewDetailBody = document.getElementById('review-detail-body');
                if (reviewContent && reviewDetailBody && nodeReviewDetailContent) {
                    reviewDetailBody.innerHTML = nodeReviewDetailContent;
                }

                // 显示弹窗
                document.getElementById('review-detail-modal-overlay').classList.add('show');
            });
        }
    }

    function showReviewWaiting() {
        const reviewDefaultView = document.getElementById('review-default');
        const reviewWaitingView = document.getElementById('review-waiting');

        if (reviewDefaultView) reviewDefaultView.style.display = 'none';
        if (reviewWaitingView) reviewWaitingView.style.display = 'flex';
    }

    function showReviewDefault() {
        const reviewDefaultView = document.getElementById('review-default');
        const reviewWaitingView = document.getElementById('review-waiting');

        if (reviewDefaultView) reviewDefaultView.style.display = 'flex';
        if (reviewWaitingView) reviewWaitingView.style.display = 'none';

        // 确保计时器停止
        stopReviewTimer();
    }

    function bindNotesPanelEvents() {
        const collapseNotesBtn = document.getElementById('collapse-notes-panel');
        const notesPanelBar = document.getElementById('notes-panel-collapsed-bar');

        if (collapseNotesBtn && notesPanelBar) {
            collapseNotesBtn.addEventListener('click', () => {
                document.querySelector('.notes-panel').classList.add('collapsed');
                notesPanelBar.classList.add('show');
            });

            notesPanelBar.addEventListener('click', () => {
                document.querySelector('.notes-panel').classList.remove('collapsed');
                notesPanelBar.classList.remove('show');
            });
        }

        const mergeBtn = document.getElementById('merge-btn');
        if (mergeBtn) {
            mergeBtn.addEventListener('click', async () => {
                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    // 先检查是否有改进笔记
                    if (!improvementDrafts || improvementDrafts.length === 0) {
                        flash('没有可合入的改进笔记');
                        return;
                    }

                    // 显示确认弹窗
                    openConfirmMergeModal();
                } else {
                    flash('保存当前章节失败，请稍后重试');
                }
            });
        }
    }

    // 打开合并确认弹窗
    function openConfirmMergeModal() {
        const confirmModalOverlay = document.getElementById('regenerate-confirm-overlay');
        if (confirmModalOverlay) {
            confirmModalOverlay.classList.add('show');
        }
    }

    function bindAiPanelEvents() {
        // 新增：绑定AI话题折叠按钮事件
        const aiTopicsToggle = document.getElementById('ai-topics-toggle');
        if (aiTopicsToggle) {
            aiTopicsToggle.addEventListener('click', toggleAiTopics);

            // 初始化按钮状态
            if (aiTopicsCollapsed) {
                aiTopicsToggle.classList.add('collapsed');
                aiTopicsToggle.setAttribute('title', '展开话题列表');
            } else {
                aiTopicsToggle.classList.remove('collapsed');
                aiTopicsToggle.setAttribute('title', '折叠话题列表');
            }
        }

        const collapseAiBtn = document.getElementById('collapse-ai-panel');
        const aiPanelBar = document.getElementById('ai-panel-collapsed-bar');

        if (collapseAiBtn && aiPanelBar) {
            collapseAiBtn.addEventListener('click', () => {
                document.querySelector('.ai-panel').classList.add('collapsed');
                aiPanelBar.classList.add('show');
            });

            aiPanelBar.addEventListener('click', () => {
                document.querySelector('.ai-panel').classList.remove('collapsed');
                aiPanelBar.classList.remove('show');
            });
        }

        const historyToggle = document.getElementById('toggle-ai-panel');
        if (historyToggle) {
            setHistoryOpen(historyToggle.classList.contains('active'));

            historyToggle.addEventListener('click', () => {
                setHistoryOpen(!isHistoryOpen);
            });
        }

        // 修改：清空历史对话按钮的处理
        const historyClearBtn = document.getElementById('ai-history-clear');
        if (historyClearBtn) {
            historyClearBtn.addEventListener('click', () => {
                openDeleteModal({
                    type: 'history-clear',
                    title: '确定清空历史对话吗？'
                });
            });
        }

        const addTopicBtn = document.getElementById('add-topic-btn');
        if (addTopicBtn) {
            addTopicBtn.addEventListener('click', () => {
                // 停止所有流式传输
                stopAllStreaming();

                // 清空聊天记录
                chatMessages = [];

                // 生成新的会话ID
                currentSessionId = `help_${Date.now()}`;
                currentMessageId = null;

                // 切换到聊天状态
                switchToChatState();
                renderChatMessages();

                // 清空输入框并聚焦
                const aiInputField = document.getElementById('ai-input-field');
                if (aiInputField) {
                    aiInputField.value = '';
                    aiInputField.focus();
                }
                updateAiPanelSendButton();
            });
        }

        // 修改：绑定"加入改进笔记"按钮点击事件
        const addToNotebookBtn = document.getElementById('add-to-notebook-btn');
        if (addToNotebookBtn) {
            addToNotebookBtn.addEventListener('click', addImprovementDraft);
        }

        const aiInputField = document.getElementById('ai-input-field');
        const aiSendBtn = document.getElementById('ai-send-btn');

        if (aiInputField && aiSendBtn) {
            aiSendBtn.addEventListener('click', () => {
                sendAiMessage(aiInputField.value);
            });

            aiInputField.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendAiMessage(aiInputField.value);
                }
            });

            aiInputField.addEventListener('input', () => {
                updateAiPanelSendButton();
            });
        }

        // 文件上传按钮事件
        const aiUploadFileTrigger = document.getElementById('ai-upload-file-trigger');
        const aiUploadFileInput = document.getElementById('ai-upload-file-input');

        if (aiUploadFileTrigger && aiUploadFileInput) {
            aiUploadFileTrigger.addEventListener('click', () => aiUploadFileInput.click());
            aiUploadFileInput.addEventListener('change', async (e) => {
                const file = e.target.files[0];
                if (file) {
                    await handleAiAttachmentUpload(file, false);
                    aiUploadFileInput.value = '';
                }
            });
        }

        // 图片上传按钮事件 - 修改：添加图片大小检查
        const aiUploadImageTrigger = document.getElementById('ai-upload-image-trigger');
        const aiUploadImageInput = document.getElementById('ai-upload-image-input');

        if (aiUploadImageTrigger && aiUploadImageInput) {
            aiUploadImageTrigger.addEventListener('click', () => aiUploadImageInput.click());
            aiUploadImageInput.addEventListener('change', async (e) => {
                const file = e.target.files && e.target.files[0];
                if (file) {
                    // 检查图片大小
                    if (!checkImageFileSize(file, true)) {
                        aiUploadImageInput.value = '';
                        return;
                    }
                    await handleAiAttachmentUpload(file, true);
                    aiUploadImageInput.value = '';
                }
            });
        }


        const materialBtn = document.querySelector('.material-text-pos');
        if (materialBtn) {
            materialBtn.addEventListener('click', async () => {
                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    document.getElementById('material-modal-overlay').classList.add('show');
                } else {
                    flash('保存当前章节失败，请稍后重试');
                }
            });
        }

        // 修正：只保留一个AI话题点击事件监听，统一在bindAiPanelEvents中处理
        const aiTopicsContent = document.getElementById('ai-topics-content');
        if (aiTopicsContent) {
            // 使用事件委托处理AI话题点击
            aiTopicsContent.addEventListener('click', async (e) => {
                const topicItem = e.target.closest('.ai-topic-item');
                if (!topicItem) return;

                const index = parseInt(topicItem.dataset.topicIndex, 10);
                const topic = aiTopicsData[index];
                if (!topic) return;

                const topicText = topic.type ? `${topic.type}：${topic.text}` : topic.text;

                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (!saved) {
                    flash('保存当前章节失败，请稍后重试');
                    return;
                }

                // 停止所有流式传输
                stopAllStreaming();

                // 清空聊天记录
                chatMessages = [];

                // 生成新的会话ID
                currentSessionId = `help_${Date.now()}`;
                currentMessageId = null;

                // 切换到聊天状态
                switchToChatState();
                renderChatMessages();

                // 设置输入框内容
                const aiInputField = document.getElementById('ai-input-field');
                if (aiInputField) {
                    aiInputField.value = topicText;
                    aiInputField.focus();
                }

                // 移除可删除的话题
                if (topic.removable) {
                    aiTopicsData.splice(index, 1);
                    renderAiTopics(aiTopicsData);
                }

                updateAiPanelSendButton();
            });
        }
    }

    function bindModalEvents() {
        const materialModal = document.getElementById('material-modal-overlay');
        const materialModalClose = document.getElementById('material-modal-close');

        if (materialModal && materialModalClose) {
            materialModalClose.addEventListener('click', () => {
                materialModal.classList.remove('show');
            });

            materialModal.addEventListener('click', (e) => {
                if (e.target === materialModal) {
                    materialModal.classList.remove('show');
                }
            });
        }

        const reviewDetailModal = document.getElementById('review-detail-modal-overlay');
        const reviewDetailClose = document.getElementById('review-detail-modal-close');

        if (reviewDetailModal && reviewDetailClose) {
            reviewDetailClose.addEventListener('click', () => {
                reviewDetailModal.classList.remove('show');
            });

            reviewDetailModal.addEventListener('click', (e) => {
                if (e.target === reviewDetailModal) {
                    reviewDetailModal.classList.remove('show');
                }
            });
        }

        bindDeleteModalEvents();
        bindSaveModalEvents();
        bindExitModalEvents();
        bindAiDialogModalEvents();
        bindAiReplyEditModalEvents();
        bindConfirmMergeModalEvents();
    }

    function bindDeleteModalEvents() {
        const deleteModal = document.getElementById('delete-file-modal-overlay');
        const deleteCancel = document.getElementById('delete-file-cancel');
        const deleteConfirm = document.getElementById('delete-file-confirm');

        let pendingDelete = null;

        window.openDeleteModal = (options) => {
            pendingDelete = options;

            const titleEl = document.getElementById('delete-file-modal-title');
            if (titleEl) {
                titleEl.textContent = options.title || '确定删除吗？';
            }

            if (deleteModal) {
                deleteModal.classList.add('show');
            }
        };

        function closeDeleteModal() {
            if (deleteModal) {
                deleteModal.classList.remove('show');
            }
            pendingDelete = null;
        }

        if (deleteCancel) {
            deleteCancel.addEventListener('click', closeDeleteModal);
        }

        if (deleteConfirm) {
            deleteConfirm.addEventListener('click', async () => {
                if (!pendingDelete) {
                    closeDeleteModal();
                    return;
                }

                try {
                    switch (pendingDelete.type) {
                        case 'note':
                            notesData = notesData.filter(note => note.id !== pendingDelete.noteId);
                            renderNotes(notesData);
                            flash('笔记已删除');
                            break;

                        case 'history':
                            historyData.splice(pendingDelete.historyIndex, 1);
                            renderHistory();
                            flash('历史对话已删除');
                            break;

                        case 'history-clear':
                            // 清空已删除的改进笔记列表（本地清空）
                            deletedImprovementDrafts = [];
                            renderHistory();
                            flash('历史对话已清空');
                            break;

                        case 'chat':
                            deleteMessage(pendingDelete.chatIndex);
                            break;

                        case 'material':
                            try {
                              const response = await fetch('/project_document/material-delete-file', {
                                method: 'DELETE',
                                headers: {
                                  'Content-Type': 'application/json',
                                  'X-CSRF-Token': ""
                                },
                                body: JSON.stringify({
                                  file_id: pendingDelete.file_id,
                                  document_id: documentId
                                })
                              });
                              const result = await response.json();
                              if (result.code === 200) {
                                  flash('素材已删除');
                                  materialData = materialData.filter(m => m.name !== pendingDelete.fileName);
                                  renderMaterialGrid();
                              } else {
                                flash(`删除失败: ${result.message}`, 'error');
                              }
                            } catch (error) {
                                console.error('删除文件失败:', error);
                                flash('删除失败，请稍后重试', 'error');
                            }

                            break;

                        case 'improvement_draft':
                            // 调用新的删除函数
                            await deleteImprovementDraft(pendingDelete.draftId);
                            break;

                        default:
                            console.warn('未知的删除类型:', pendingDelete.type);
                            flash('未知操作');
                    }
                } catch (error) {
                    console.error('删除失败:', error);
                    flash('删除失败: ' + error.message);
                } finally {
                    closeDeleteModal();
                }
            });
        }

        if (deleteModal) {
            deleteModal.addEventListener('click', (e) => {
                if (e.target === deleteModal) {
                    closeDeleteModal();
                }
            });
        }
    }

    function deleteMessage(index) {
        if (index >= 0 && index < chatMessages.length) {
            chatMessages.splice(index, 1);
            renderChatMessages();
            flash('消息已删除');
        }
    }

    function copyMessage(index) {
        if (index >= 0 && index < chatMessages.length) {
            const msg = chatMessages[index];
            const text = msg.text || '';

            navigator.clipboard.writeText(text).then(() => {
                flash('已复制到剪贴板');
            }).catch(err => {
                console.error('复制失败:', err);
                flash('复制失败');
            });
        }
    }

    function bindSaveModalEvents() {
        const saveModalOverlay = document.getElementById('save-modal-overlay');
        const saveModalCancel = document.getElementById('save-modal-cancel');
        const saveModalConfirm = document.getElementById('save-modal-confirm');

        if (saveModalOverlay && saveModalCancel && saveModalConfirm) {
            window.openSaveModal = () => {
                saveModalOverlay.classList.add('show');
            };

            const closeSaveModal = () => {
                saveModalOverlay.classList.remove('show');
            };

            saveModalCancel.addEventListener('click', closeSaveModal);

            saveModalConfirm.addEventListener('click', () => {
                closeSaveModal();
                openArchiveProgressModal();
            });

            saveModalOverlay.addEventListener('click', (e) => {
                if (e.target === saveModalOverlay) closeSaveModal();
            });
        }
    }

    function bindExitModalEvents() {
        const exitModalOverlay = document.getElementById('exit-modal-overlay');
        const exitModalDiscard = document.getElementById('exit-modal-discard');
        const exitModalContinue = document.getElementById('exit-modal-continue');
        const exitModalSave = document.getElementById('exit-modal-save');

        if (exitModalOverlay && exitModalDiscard && exitModalContinue && exitModalSave) {
            window.openExitModal = () => {
                exitModalOverlay.classList.add('show');
            };

            const closeExitModal = () => {
                exitModalOverlay.classList.remove('show');
            };

            exitModalDiscard.addEventListener('click', () => {
                closeExitModal();
                window.location.href = '/';
            });

            exitModalContinue.addEventListener('click', closeExitModal);

            exitModalSave.addEventListener('click', async () => {
                // 保存当前章节内容
                const saved = await saveCurrentSection();
                if (saved) {
                    closeExitModal();
                    openArchiveProgressModal();
                    setTimeout(() => {
                        window.location.href = '/';
                    }, 1000);
                } else {
                    flash('保存失败，请稍后重试');
                }
            });

            exitModalOverlay.addEventListener('click', (e) => {
                if (e.target === exitModalOverlay) closeExitModal();
            });
        }
    }

    function bindAiDialogModalEvents() {
        const aiDialogOverlay = document.getElementById('ai-dialog-modal-overlay');
        const aiDialogClose = document.getElementById('ai-dialog-close');
        const aiDialogContent = document.getElementById('ai-dialog-content');
        const aiDialogInput = document.getElementById('ai-dialog-input');
        const aiDialogSend = document.getElementById('ai-dialog-send');

        if (aiDialogOverlay && aiDialogClose && aiDialogContent && aiDialogInput && aiDialogSend) {
            let dialogMessages = [];
            let originalText = '';
            let aiGeneratedText = '';

            const renderDialogMessages = () => {
                if (!aiDialogContent) return;

                aiDialogContent.innerHTML = dialogMessages.map((msg, index) => {
                    if (msg.type === 'ai') {
                        return `
                            <div class="ai-dialog-message-ai">
                                <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                                <div class="ai-dialog-message-content">
                                    <div class="ai-dialog-bubble-ai">
                                        <span class="ai-dialog-text">${msg.text}</span>
                                        <span class="ai-dialog-hint">以上内容由AI生成</span>
                                    </div>
                                    <img class="ai-dialog-reference" data-index="${index}" src="/static/project_document/images/common/icon-reference.png" />
                                </div>
                            </div>
                        `;
                    } else if (msg.type === 'user') {
                        return `
                            <div class="ai-dialog-message-user">
                                <div class="ai-dialog-bubble-user">
                                    <span class="ai-dialog-text">${msg.text}</span>
                                </div>
                                <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-assistant.png" />
                            </div>
                        `;
                    } else if (msg.type === 'loading') {
                        return `
                            <div class="ai-dialog-message-ai">
                                <img class="ai-dialog-avatar" src="/static/project_document/images/common/avatar-default.png" />
                                <div class="ai-dialog-loading-dots">
                                    <span class="dot"></span>
                                    <span class="dot"></span>
                                    <span class="dot"></span>
                                </div>
                            </div>
                        `;
                    }
                }).join('');

                aiDialogContent.scrollTop = aiDialogContent.scrollHeight;
            };

            window.openAiDialog = (action, selectedText, customQuestion = '') => {
                dialogMessages = [];
                originalText = selectedText;

                let aiQuestion = '';
                if (action === '续写') {
                    aiQuestion = `我看到你选中了这段文字："${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"。我可以帮你续写后续内容，你希望续写的方向是什么？`;
                } else if (action === '扩写') {
                    aiQuestion = `我看到你选中了这段文字："${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"。我可以帮你扩写更详细的内容，你希望重点扩展哪些方面？`;
                } else if (action === '缩写') {
                    aiQuestion = `我看到你选中了这段文字："${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"。我可以帮你精简内容，你希望保留哪些核心要点？`;
                } else if (action === '改写') {
                    aiQuestion = `我看到你选中了这段文字："${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"。我可以帮你改写这段内容，你希望改写成什么风格或方向？`;
                } else if (action === '自定义提问') {
                    aiQuestion = `关于你选中的文字："${selectedText.substring(0, 50)}${selectedText.length > 50 ? '...' : ''}"，你的问题是：${customQuestion}`;
                } else if (action === '悬浮球') {
                    aiQuestion = '已打开对话，可以直接输入问题。';
                }

                if (aiQuestion) {
                    dialogMessages.push({
                        type: 'ai',
                        text: aiQuestion,
                        hasReference: false
                    });
                }

                renderDialogMessages();
                aiDialogOverlay.classList.add('show');
                aiDialogInput.value = '';
                aiDialogInput.focus();
            };

            const closeAiDialog = () => {
                aiDialogOverlay.classList.remove('show');
                dialogMessages = [];
            };

            const sendDialogMessage = () => {
                const userInput = aiDialogInput.value.trim();
                if (!userInput) return;

                dialogMessages.push({
                    type: 'user',
                    text: userInput
                });

                dialogMessages.push({
                    type: 'loading'
                });

                renderDialogMessages();
                aiDialogInput.value = '';

                setTimeout(() => {
                    dialogMessages = dialogMessages.filter(msg => msg.type !== 'loading');

                    const aiResponses = [
                        '感知自然：认知心理学所述，约 80% 外界信息通过视觉通道获取。界面设计中最重要的视觉要素，包括布局、色彩、插画、图标等，应充分汲取自然界规律，从而降低用户认知成本，带来真实流畅的感受。在一些场景下，适时加入听觉、触觉等其它感知通道，能创造更丰富自然的产品体验。',
                        '基于你的需求，我建议从以下几个方面展开：首先明确核心观点，然后通过具体案例支撑论述，最后总结升华主题。这样的结构能够让读者更容易理解和接受你的观点。',
                        '这是一个很好的想法！我们可以从用户体验的角度出发，结合实际应用场景来完善这部分内容。建议增加一些具体的数据支撑，让论述更有说服力。'
                    ];

                    const aiReply = aiResponses[Math.floor(Math.random() * aiResponses.length)];
                    aiGeneratedText = aiReply;

                    dialogMessages.push({
                        type: 'ai',
                        text: aiReply,
                        hasReference: Math.random() > 0.5
                    });

                    renderDialogMessages();
                }, 1000);
            };

            aiDialogClose.addEventListener('click', closeAiDialog);
            aiDialogOverlay.addEventListener('click', (e) => {
                if (e.target === aiDialogOverlay) closeAiDialog;
            });

            aiDialogContent.addEventListener('click', (e) => {
                const target = e.target.closest('.ai-dialog-reference');
                if (!target) return;
                const index = Number(target.dataset.index);
                if (Number.isNaN(index)) return;
                const msg = dialogMessages[index];
                if (msg && msg.text) {
                    navigator.clipboard.writeText(msg.text).then(() => {
                        flash('已复制');
                    });
                }
            });
        }
    }

    function bindAiReplyEditModalEvents() {
        const aiReplyEditModal = document.getElementById('ai-reply-edit-overlay');
        const aiReplyEditClose = document.getElementById('ai-reply-edit-close');
        const aiReplyEditCancel = document.getElementById('ai-reply-edit-cancel');
        const aiReplyEditSave = document.getElementById('ai-reply-edit-save');

        let editingIndex = null;

        window.openReplyEditModal = (index) => {
            if (index < 0 || index >= chatMessages.length) return;

            const msg = chatMessages[index];
            if (msg.type !== 'ai') return;

            editingIndex = index;
            editingMessageData = {
                session_id: currentSessionId,
                message_id: msg.id || `msg_${Date.now()}`,
                document_id: documentId
            };

            initAiReplyEditEditor();

            if (aiReplyEditEditor && msg.text) {
                if (aiReplyEditEditor.setHtml) {
                    aiReplyEditEditor.setHtml(msg.text);
                } else if (aiReplyEditEditor.setText) {
                    aiReplyEditEditor.setText(msg.text);
                }
            }

            if (aiReplyEditModal) {
                aiReplyEditModal.classList.add('show');
            }
        };

        function closeAiReplyEditModal() {
            if (aiReplyEditModal) {
                aiReplyEditModal.classList.remove('show');
            }
            editingIndex = null;
        }

        async function saveAiReplyEdit() {
            if (editingIndex === null || !aiReplyEditEditor || !editingMessageData) return;

            const msg = chatMessages[editingIndex];
            if (!msg) return;

            let newText = '';
            if (aiReplyEditEditor.getHtml) {
                newText = aiReplyEditEditor.getHtml();
            } else if (aiReplyEditEditor.getText) {
                newText = aiReplyEditEditor.getText();
            }

            if (!newText) {
                flash('编辑内容不能为空');
                return;
            }

            try {
                // 保存到后端数据库
                const result = await DataService.updateConversationMessage({
                    document_id: editingMessageData.document_id,
                    session_id: editingMessageData.session_id,
                    message_id: editingMessageData.message_id,
                    content: newText
                });

                // 更新本地消息内容
                msg.text = newText;
                renderChatMessages();

                flash('AI回复已保存到数据库');
                closeAiReplyEditModal();

            } catch (error) {
                console.error('保存AI回复失败:', error);
                flash('保存失败: ' + error.message);
            }
        }

        if (aiReplyEditClose) {
            aiReplyEditClose.addEventListener('click', closeAiReplyEditModal);
        }

        if (aiReplyEditCancel) {
            aiReplyEditCancel.addEventListener('click', closeAiReplyEditModal);
        }

        if (aiReplyEditSave) {
            aiReplyEditSave.addEventListener('click', saveAiReplyEdit);
        }
    }

    function initAiReplyEditEditor() {
        if (aiReplyEditEditor || !window.wangEditor) return;

        const { createEditor, createToolbar } = window.wangEditor;

        aiReplyEditEditor = createEditor({
            selector: '#ai-reply-edit-editor',
            html: '',
            config: {
                placeholder: '编辑AI回复内容...',
                MENU_CONF: {
                    uploadImage: {
                        maxFileSize: MAX_IMAGE_SIZE, // 5MB限制
                        async customUpload(file, insertFn) {
                            try {
                                // 检查图片大小
                                if (file.size > MAX_IMAGE_SIZE) {
                                    flash('图片大小不能超过5MB');
                                    return;
                                }

                                // 修改：使用 uploadImg 而不是 uploadFile
                                const result = await DataService.uploadImg(file);
                                if (result.code === 200 || result.code === 1) {
                                    const url = result.data?.url || result.url;
                                    insertFn(url, file.name);
                                    flash('图片上传成功');
                                } else {
                                    flash('图片上传失败');
                                }
                            } catch (error) {
                                flash('上传失败: ' + error.message);
                            }
                        },
                    },
                },
            },
            mode: 'default',
        });

        createToolbar({
            editor: aiReplyEditEditor,
            selector: '#ai-reply-edit-toolbar',
            mode: 'default',
        });
    }

    // ==================== 选中文字悬浮工具栏 ====================
    function bindSelectionToolbarEvents() {
        const selectionToolbar = document.getElementById('selection-toolbar');
        const selectionToolbarResult = document.getElementById('selection-toolbar-result');
        const editorContent = document.getElementById('editor-content');
        const floatBallToggle = document.getElementById('toggle-float-ball');

        if (!selectionToolbar || !selectionToolbarResult || !editorContent) return;

        const isFloatBallEnabled = () => {
            return floatBallToggle && floatBallToggle.classList.contains('active');
        };

        editorScrollContainer = editorContent.closest('.flex-col.self-stretch.relative');
        if (editorScrollContainer && getComputedStyle(editorScrollContainer).position === 'static') {
            editorScrollContainer.style.position = 'relative';
        }

        const createHighlightOverlay = (rects) => {
            removeHighlightOverlay();

            if (!rects || rects.length === 0) return;

            const container = document.createElement('div');
            container.className = 'selection-highlight-container';

            const targetContainer = editorScrollContainer || document.body;
            const containerRect = editorScrollContainer ?
                editorScrollContainer.getBoundingClientRect() :
                { left: 0, top: 0, scrollLeft: 0, scrollTop: 0 };

            rects.forEach(rect => {
                if (rect.width === 0 || rect.height === 0) return;

                const div = document.createElement('div');
                div.className = 'selection-highlight-overlay';

                let left, top;
                if (editorScrollContainer) {
                    left = rect.left - containerRect.left + editorScrollContainer.scrollLeft;
                    top = rect.top - containerRect.top + editorScrollContainer.scrollTop;
                } else {
                    left = rect.left + window.scrollX;
                    top = rect.top + window.scrollY;
                }

                div.style.left = left + 'px';
                div.style.top = top + 'px';
                div.style.width = rect.width + 'px';
                div.style.height = rect.height + 'px';
                container.appendChild(div);
            });

            if (container.children.length > 0) {
                targetContainer.appendChild(container);
                highlightOverlay = container;
            }
        };

        const removeHighlightOverlay = () => {
            if (highlightOverlay) {
                highlightOverlay.remove();
                highlightOverlay = null;
            }
        };

        const updateHighlightOverlay = () => {
            if (!selectedRange) {
                removeHighlightOverlay();
                return;
            }

            const rects = Array.from(selectedRange.getClientRects());
            if (!rects.length) {
                removeHighlightOverlay();
                return;
            }

            createHighlightOverlay(rects);
        };

        let pendingSelectionUpdate = null;
        const scheduleSelectionUpdate = () => {
            if (pendingSelectionUpdate) {
                window.cancelAnimationFrame(pendingSelectionUpdate);
            }
            pendingSelectionUpdate = window.requestAnimationFrame(() => {
                pendingSelectionUpdate = null;
                updateHighlightOverlay();
                updateToolbarPosition();
            });
        };

        const updateToolbarPosition = (rect) => {
            if (!rect && selectedRange) {
                rect = selectedRange.getBoundingClientRect();
            }

            if (!rect || (rect.width === 0 && rect.height === 0)) {
                return;
            }

            const toolbarWidth = 240;
            let left = rect.left + (rect.width / 2) - (toolbarWidth / 2);
            let top = rect.bottom + 10;

            if (left < 10) left = 10;
            if (left + toolbarWidth > window.innerWidth - 10) {
                left = window.innerWidth - toolbarWidth - 10;
            }

            if (top + 100 > window.innerHeight) {
                top = rect.top - 100;
                if (top < 10) top = 10;
            }

            selectionToolbar.style.left = left + 'px';
            selectionToolbar.style.top = top + 'px';
            selectionToolbarResult.style.left = left + 'px';
            selectionToolbarResult.style.top = top + 'px';
        };

        const hideToolbar = (force = false) => {
            if (isAiSuggestionPending && !force) {
                flash('请先采用或弃用当前结果');
                return;
            }

            selectionToolbar.style.display = 'none';
            selectionToolbarResult.style.display = 'none';
            selectedText = '';
            selectedRange = null;
            currentHighlightNode = null;
            selectionToolbar.querySelector('.selection-input').value = '';
            selectionToolbarResult.querySelector('.selection-input').value = '';
            removeHighlightOverlay();
            isAiSuggestionPending = false;
            currentOriginalText = '';
            currentAIGeneratedText = '';
            currentAIOperation = '';
        };

        const insertAIGeneratedContent = (operation, originalText, aiContent) => {
            if (!selectedRange || !originalText) return null;

            try {
                currentOriginalText = originalText;
                currentAIGeneratedText = aiContent;
                currentAIOperation = operation;

                const highlightSpan = document.createElement('span');
                highlightSpan.className = 'ai-generated-highlight';
                highlightSpan.textContent = aiContent;

                if (operation === '扩写') {
                    const range = selectedRange.cloneRange();
                    const tempSpan = document.createElement('span');
                    tempSpan.textContent = originalText + aiContent;

                    range.deleteContents();
                    range.insertNode(tempSpan);

                    const newRange = document.createRange();
                    newRange.selectNodeContents(tempSpan);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(newRange);

                    tempSpan.className = 'ai-generated-highlight';
                    currentHighlightNode = tempSpan;
                    selectedRange = newRange;

                    return tempSpan;
                } else if (operation === '缩写') {
                    const range = selectedRange.cloneRange();

                    range.deleteContents();
                    range.insertNode(highlightSpan);

                    const newRange = document.createRange();
                    newRange.selectNodeContents(highlightSpan);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(newRange);

                    currentHighlightNode = highlightSpan;
                    selectedRange = newRange;

                    return highlightSpan;
                } else if (operation === '改写') {
                    const range = selectedRange.cloneRange();

                    range.deleteContents();
                    range.insertNode(highlightSpan);

                    const newRange = document.createRange();
                    newRange.selectNodeContents(highlightSpan);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(newRange);

                    currentHighlightNode = highlightSpan;
                    selectedRange = newRange;

                    return highlightSpan;
                } else if (operation === '自定义提问') {
                    const range = selectedRange.cloneRange();
                    const tempSpan = document.createElement('span');
                    tempSpan.textContent = originalText + '\n\n' + aiContent;

                    range.deleteContents();
                    range.insertNode(tempSpan);

                    const newRange = document.createRange();
                    newRange.selectNodeContents(tempSpan);
                    window.getSelection().removeAllRanges();
                    window.getSelection().addRange(newRange);

                    tempSpan.className = 'ai-generated-highlight';
                    currentHighlightNode = tempSpan;
                    selectedRange = newRange;

                    return tempSpan;
                }
            } catch (error) {
                console.error('插入AI内容失败:', error);
                return null;
            }
        };

        const generateAndShowAIContent = (operation, originalText, customQuestion = '') => {
            if (!originalText) {
                flash('请先选择文本');
                return;
            }

            selectionToolbar.style.display = 'none';

            let aiContent = '';

            switch (operation) {
                case '扩写':
                    aiContent = `\n\n${originalText} 的详细阐述如下：界面设计的核心在于模拟自然规律。研究显示，人类通过视觉获取的信息占比高达80%。因此，优秀的界面设计应当充分利用布局、色彩、图标等视觉元素，创造流畅自然的用户体验。在适当场景下，结合听觉、触觉等多感官反馈，能够进一步提升产品的沉浸感。`;
                    break;

                case '缩写':
                    aiContent = originalText.length > 100 ?
                        originalText.substring(0, 50) + '...（已精简至核心内容）' :
                        originalText.substring(0, Math.floor(originalText.length / 2)) + '...';
                    break;

                case '改写':
                    aiContent = `改写后的内容：界面设计应当遵循自然规律以降低认知成本。研究表明，视觉信息处理占人类信息接收的80%。因此，设计师应通过合理的布局、色彩和视觉层次来创造直观流畅的用户体验，并在合适场景中整合多感官元素来增强产品吸引力。`;
                    break;

                case '自定义提问':
                    aiContent = `针对您的问题"${customQuestion}"，我的回答是：${originalText} 这段内容可以从认知心理学、用户体验设计和实际应用案例三个维度进行深入分析。建议结合实际数据支撑您的观点，使论述更具说服力。`;
                    break;

                default:
                    aiContent = `基于您选中的内容"${originalText.substring(0, 50)}..."，AI生成的相关建议：请结合上下文进行适当调整。`;
            }

            const result = insertAIGeneratedContent(operation, originalText, aiContent);

            if (result) {
                isAiSuggestionPending = true;
                showResultToolbar();

                updateHighlightOverlay();

                setTimeout(() => {
                    if (selectedRange) {
                        const rect = selectedRange.getBoundingClientRect();
                        updateToolbarPosition(rect);
                    }
                }, 50);
            }
        };

        const showResultToolbar = () => {
            selectionToolbar.style.display = 'none';
            selectionToolbarResult.style.display = 'flex';
            if (selectedRange) {
                const rect = selectedRange.getBoundingClientRect();
                updateToolbarPosition(rect);
            }
        };

        const discardAIContent = () => {
            if (!currentHighlightNode || !currentOriginalText) return;

            try {
                const textNode = document.createTextNode(currentOriginalText);
                currentHighlightNode.parentNode.replaceChild(textNode, currentHighlightNode);

                const range = document.createRange();
                range.selectNodeContents(textNode);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
                selectedRange = range;

                flash('已弃用AI生成内容');
                hideToolbar(true);
            } catch (error) {
                console.error('弃用失败:', error);
                flash('弃用失败');
            }
        };

        const adoptAIContent = () => {
            if (!currentHighlightNode || !currentAIGeneratedText) return;

            try {
                const textNode = document.createTextNode(currentAIGeneratedText);
                currentHighlightNode.parentNode.replaceChild(textNode, currentHighlightNode);

                const range = document.createRange();
                range.selectNodeContents(textNode);
                window.getSelection().removeAllRanges();
                window.getSelection().addRange(range);
                selectedRange = range;

                flash('已采用AI生成内容');
                hideToolbar(true);
            } catch (error) {
                console.error('采用失败:', error);
                flash('采用失败');
            }
        };

        selectionToolbar.addEventListener('mousedown', (e) => {
            if (!e.target.classList.contains('selection-input')) {
                e.preventDefault();
            }
        });
        selectionToolbarResult.addEventListener('mousedown', (e) => {
            if (!e.target.classList.contains('selection-input')) {
                e.preventDefault();
            }
        });

        if (editorScrollContainer) {
            editorScrollContainer.addEventListener('scroll', scheduleSelectionUpdate);
        }
        window.addEventListener('resize', scheduleSelectionUpdate);

        document.addEventListener('mouseup', (e) => {
            if (selectionToolbar.contains(e.target) || selectionToolbarResult.contains(e.target)) return;

            if (isAiSuggestionPending) {
                flash('请先采用或弃用当前结果');
                return;
            }

            if (ignoreSelectionOnce) {
                ignoreSelectionOnce = false;
                return;
            }

            if (!isFloatBallEnabled()) {
                hideToolbar();
                return;
            }

            setTimeout(() => {
                const selection = window.getSelection();
                const text = selection.toString().trim();

                if (text.length > 0) {
                    const range = selection.getRangeAt(0);
                    const container = range.commonAncestorContainer;
                    const isInEditor = editorContent.contains(container) ||
                                      container === editorContent ||
                                      (container.nodeType === 3 && editorContent.contains(container.parentNode));

                    if (isInEditor) {
                        selectedText = text;
                        selectedRange = range.cloneRange();

                        const rect = range.getBoundingClientRect();
                        const rects = Array.from(range.getClientRects());
                        createHighlightOverlay(rects);

                        window.getSelection().removeAllRanges();
                        window.getSelection().addRange(range);

                        updateToolbarPosition(rect);
                        selectionToolbar.style.display = 'flex';
                        selectionToolbarResult.style.display = 'none';
                    }
                } else if (!selectionToolbar.contains(e.target) && !selectionToolbarResult.contains(e.target)) {
                    hideToolbar();
                }
            }, 10);
        });

        selectionToolbar.querySelectorAll('.selection-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                if (isAiSuggestionPending) {
                    flash('请先采用或弃用当前结果');
                    return;
                }
                const action = btn.dataset.action;
                generateAndShowAIContent(action, selectedText);
            });
        });

        selectionToolbar.querySelector('.selection-send-icon').addEventListener('click', () => {
            if (isAiSuggestionPending) {
                flash('请先采用或弃用当前结果');
                return;
            }
            const input = selectionToolbar.querySelector('.selection-input').value.trim();
            if (input) {
                generateAndShowAIContent('自定义提问', selectedText, input);
            }
        });

        document.getElementById('btn-discard').addEventListener('click', discardAIContent);

        document.getElementById('btn-adopt').addEventListener('click', adoptAIContent);

        selectionToolbarResult.querySelector('.selection-send-icon').addEventListener('click', () => {
            const input = selectionToolbarResult.querySelector('.selection-input').value.trim();
            if (input) {
                flash(`继续提问: ${input}`);
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                hideToolbar();
            }
        });

        editorContent.addEventListener('dblclick', (e) => {
            if (!isFloatBallEnabled()) return;
            e.preventDefault();
            e.stopPropagation();
            const selection = window.getSelection();
            if (selection) selection.removeAllRanges();
            hideToolbar();
            if (typeof window.openAiDialog === 'function') {
                window.openAiDialog('悬浮球', '');
            }
        });

        editorContent.addEventListener('contextmenu', (e) => {
            if (!isFloatBallEnabled()) return;
            e.preventDefault();
            if (floatBallToggle) floatBallToggle.classList.remove('active');
            hideToolbar(true);
        });
    }

    // ==================== 使用CSS变量的拖拽逻辑 ====================
    function bindResizeEvents() {
        const resizeHandle = document.getElementById('resize-handle');
        const leftPanel = document.querySelector('.outline-panel');

        if (!resizeHandle || !leftPanel) return;

        const dragCursor = document.createElement('div');
        dragCursor.className = 'drag-cursor';
        document.body.appendChild(dragCursor);

        const minWidth = 15;
        const maxWidth = 35;
        const remSize = parseFloat(getComputedStyle(document.documentElement).fontSize);

        const applyWidth = (widthRem) => {
            setCssVar(CSS_VARS.OUTLINE_WIDTH, `${widthRem}rem`);

            leftPanel.style.width = `var(${CSS_VARS.OUTLINE_WIDTH})`;
            leftPanel.style.flexBasis = `var(${CSS_VARS.OUTLINE_WIDTH})`;
            leftPanel.style.minWidth = `var(${CSS_VARS.OUTLINE_WIDTH})`;

            leftPanel.offsetHeight;
        };

        resizeHandle.addEventListener('mousedown', (e) => {
            isResizing = true;
            isDraggingResizeHandle = true;
            startX = e.clientX;
            startWidth = leftPanel.offsetWidth;
            resizeHandle.classList.add('dragging');
            document.body.classList.add('dragging-resize');
            document.body.style.userSelect = 'none';

            dragCursor.classList.add('active');
            dragCursor.style.left = e.clientX + 'px';
            dragCursor.style.top = e.clientY + 'px';

            e.preventDefault();
        });

        document.addEventListener('mousemove', (e) => {
            if (!isDraggingResizeHandle) return;

            dragCursor.style.left = e.clientX + 'px';
            dragCursor.style.top = e.clientY + 'px';

            const deltaX = e.clientX - startX;
            const newWidth = startWidth + deltaX;
            const newWidthRem = newWidth / remSize;

            if (newWidthRem >= minWidth && newWidthRem <= maxWidth) {
                applyWidth(newWidthRem);
            }
        });

        document.addEventListener('mouseup', () => {
            if (isDraggingResizeHandle) {
                isResizing = false;
                isDraggingResizeHandle = false;
                resizeHandle.classList.remove('dragging');
                document.body.classList.remove('dragging-resize');
                document.body.style.userSelect = '';
                dragCursor.classList.remove('active');

                saveCssVars();
            }
        });

        resizeHandle.addEventListener('selectstart', (e) => {
            e.preventDefault();
        });

        window.addEventListener('resize', () => {
            const currentWidth = getCssVar(CSS_VARS.OUTLINE_WIDTH);
            if (currentWidth) {
                leftPanel.style.width = `var(${CSS_VARS.OUTLINE_WIDTH})`;
                leftPanel.style.flexBasis = `var(${CSS_VARS.OUTLINE_WIDTH})`;
                leftPanel.style.minWidth = `var(${CSS_VARS.OUTLINE_WIDTH})`;
            }
        });
    }

    // ==================== 自动保存功能 ====================
    function startAutoSave() {
        autoSaveInterval = setInterval(() => {
            if (currentSectionNodeId && document.visibilityState === 'visible') {
                saveCurrentSection();
            }
        }, 30000);

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'hidden' && currentSectionNodeId) {
                saveCurrentSection();
            }
        });

        window.addEventListener('beforeunload', () => {
            if (currentSectionNodeId) {
                saveCurrentSectionSync();
            }
        });
    }

    function saveCurrentSectionSync() {
        console.log('同步保存当前章节');
    }

    // ==================== 业务逻辑函数 ====================
    async function downloadMaterial(fileName) {
        try {
            const blob = new Blob([`示例文件内容：${fileName}`], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `${fileName}`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);

            flash(`已开始下载：${fileName}`);
        } catch (error) {
            console.error('下载文件失败:', error);
            flash('下载文件失败');
        }
    }

    async function startSectionReview(node_id) {
        try {
            startReviewTimer();
            showReviewWaiting();

            const result = await DataService.reviewSection({
                document_id: documentId,
                node_id: node_id,
                session_id: `review_${Date.now()}`
            });

            stopReviewTimer();

            // 传入当前评审范围到renderReviewFromResponse函数
            renderReviewFromResponse(result, currentReviewScope);

            showReviewDefault();
            flash('章节评审完成');

            // 评审完成后，标记评审已完成
            markReviewCompleted();
        } catch (error) {
            console.error('章节评审失败:', error);
            stopReviewTimer();
            showReviewDefault();
            flash('章节评审失败: ' + error.message);
        }
    }

    // ==================== 评审计时函数 ====================
    function startReviewTimer() {
        stopReviewTimer();

        reviewSeconds = 0;

        updateReviewTimerDisplay();

        reviewTimerInterval = setInterval(() => {
            reviewSeconds++;
            updateReviewTimerDisplay();
        }, 1000);
    }

    function stopReviewTimer() {
        if (reviewTimerInterval) {
            clearInterval(reviewTimerInterval);
            reviewTimerInterval = null;
        }
    }

    function updateReviewTimerDisplay() {
        const minutes = Math.floor(reviewSeconds / 60);
        const seconds = reviewSeconds % 60;

        const formattedTime =
            minutes.toString().padStart(2, '0') + ':' +
            seconds.toString().padStart(2, '0');

        const reviewWaitingTime = document.querySelector('.review-waiting-time');
        if (reviewWaitingTime) {
            reviewWaitingTime.textContent = formattedTime;
        }
    }

    // ==================== 加载状态管理 ====================
    function showLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (!loadingOverlay) {
            const overlay = document.createElement('div');
            overlay.id = 'loading-overlay';
            overlay.className = 'loading-overlay';
            overlay.innerHTML = `
                <div class="loading-spinner"></div>
                <div class="loading-text">加载中...</div>
            `;
            document.body.appendChild(overlay);
        } else {
            loadingOverlay.style.display = 'flex';
        }
    }

    function hideLoading() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    }

    function showError(message) {
        const errorOverlay = document.getElementById('error-overlay');
        if (!errorOverlay) {
            const overlay = document.createElement('div');
            overlay.id = 'error-overlay';
            overlay.className = 'error-overlay';
            overlay.innerHTML = `
                <div class="error-content">
                    <div class="error-icon">⚠️</div>
                    <div class="error-message">${message}</div>
                    <button class="error-retry" onclick="location.reload()">重新加载</button>
                    <button class="error-close" onclick="document.getElementById('error-overlay').style.display='none'">关闭</button>
                </div>
            `;
            document.body.appendChild(overlay);
        } else {
            errorOverlay.style.display = 'flex';
        }
    }

    // ==================== 页面卸载清理 ====================
    function cleanup() {
        if (autoSaveInterval) {
            clearInterval(autoSaveInterval);
            autoSaveInterval = null;
        }

        if (reviewTimerInterval) {
            clearInterval(reviewTimerInterval);
            reviewTimerInterval = null;
        }

        // 停止合并计时器
        stopMergeTimer();

        stopAllStreaming();

        // 停止启发式写作流
        if (heuristicStreamHandler) {
            heuristicStreamHandler.cancel();
            heuristicStreamHandler = null;
        }

        if (mainEditor && mainEditor.destroy) {
            mainEditor.destroy();
        }

        if (aiReplyEditEditor && aiReplyEditEditor.destroy) {
            aiReplyEditEditor.destroy();
        }

        const aiPanel = document.querySelector('.ai-panel');
        if (aiPanel) {
            localStorage.setItem('panel_ai_collapsed', aiPanel.classList.contains('collapsed').toString());
        }
    }

    // ==================== 存档弹窗相关 ====================
    const openArchiveProgressModal = () => {
        const archiveProgressOverlay = document.getElementById('archive-progress-overlay');
        if (archiveProgressOverlay) {
            archiveProgressOverlay.classList.add('show');
            document.body.classList.add('modal-open');
        }
    };

    const closeArchiveProgressModal = () => {
        const archiveProgressOverlay = document.getElementById('archive-progress-overlay');
        if (archiveProgressOverlay) {
            archiveProgressOverlay.classList.remove('show');
            document.body.classList.remove('modal-open');
        }
    };

    const archiveProgressCancel = document.getElementById('archive-progress-cancel');
    const archiveProgressConfirm = document.getElementById('archive-progress-confirm');
    const archiveProgressCloseImg = document.getElementById('archive-progress-close-img');

    if (archiveProgressCancel) {
        archiveProgressCancel.addEventListener('click', closeArchiveProgressModal);
    }

    if (archiveProgressConfirm) {
        archiveProgressConfirm.addEventListener('click', () => {
            flash('已存档');
            closeArchiveProgressModal();
        });
    }
    if (archiveProgressCloseImg) {
        archiveProgressCloseImg.addEventListener('click', closeArchiveProgressModal);
    }

    // ==================== 初始化执行 ====================
    window.addEventListener('unload', cleanup);
    initialize();
});