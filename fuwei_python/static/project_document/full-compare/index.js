// static/project_document/full-compare/index.js
document.addEventListener('DOMContentLoaded', function () {
    // ==================== Markdown转换工具 ====================
    // 检查是否加载了Markdown处理器
    const markdownProcessor = window.MarkdownProcessor || {};

    /**
     * 处理编辑器内容中的Markdown
     * @param {string} content 编辑器内容
     * @returns {string} 处理后的HTML内容
     */
    function processEditorContent(content) {
        if (!content || typeof content !== 'string') return content || '';

        // 检查内容是否为Markdown格式
        if (markdownProcessor.isMarkdown && markdownProcessor.isMarkdown(content)) {
            console.log('检测到Markdown格式内容，正在转换...');
            const htmlContent = markdownProcessor.markdownToHtml
                ? markdownProcessor.markdownToHtml(content)
                : marked.parse(content);

            // 如果是在页面上使用flash函数，可以调用它
            if (typeof flash === 'function') {
                flash('Markdown格式已自动转换为HTML');
            }
            return htmlContent;
        }

        return content;
    }

    /**
     * 自定义粘贴处理器
     * @param {Object} editor 编辑器实例
     * @param {Event} event 粘贴事件
     */
    function customPasteHandler(editor, event) {
        event.preventDefault();
        event.stopPropagation();  // 阻止事件冒泡

        const clipboardData = event.clipboardData || window.clipboardData;
        if (!clipboardData) return;

        let text = clipboardData.getData('text/plain') || '';
        let html = clipboardData.getData('text/html') || '';

        // 如果没有HTML但有文本，检查是否为Markdown
        if (!html && text) {
            if (markdownProcessor.isMarkdown && markdownProcessor.isMarkdown(text)) {
                html = markdownProcessor.markdownToHtml
                    ? markdownProcessor.markdownToHtml(text)
                    : marked.parse(text);
                console.log('Markdown已转换为HTML');
                if (typeof flash === 'function') {
                    flash('Markdown格式已自动转换为HTML');
                }
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
    }

    // ==================== 主要功能 ====================
    // 数据服务引用
    const DataService = window.ProjectDocumentService;

    // 当前节点ID，从URL参数获取
    let currentSectionNodeId = null;

    // 获取URL参数中的node_id
    function getNodeIdFromUrl() {
        const params = new URLSearchParams(window.location.search);
        return params.get('node_id');
    }

    // ==================== 工具函数 ====================
    // 获取CSRF token
    function getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // Toast提示函数
    function flash(text, type = 'info') {
        const hint = document.createElement('div');
        hint.className = `toast-hint toast-${type}`;
        hint.innerText = text;

        // 添加到页面
        const container = document.getElementById('toast-container') || document.body;
        container.appendChild(hint);

        // 显示
        setTimeout(() => {
            hint.classList.add('show');
        }, 10);

        // 3秒后隐藏并移除
        setTimeout(() => {
            hint.classList.remove('show');
            setTimeout(() => {
                if (hint.parentNode) {
                    hint.parentNode.removeChild(hint);
                }
            }, 200);
        }, 3000);
    }

    // 显示/隐藏加载状态
    function showLoading(show) {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (show) {
            if (!loadingOverlay) {
                const loadingDiv = document.createElement('div');
                loadingDiv.id = 'loading-overlay';
                loadingDiv.className = 'loading-overlay';
                loadingDiv.innerHTML =
                    '<div class="loading-spinner"></div>' +
                    '<div class="loading-text">加载中...</div>';
                document.body.appendChild(loadingDiv);
            } else {
                loadingOverlay.style.display = 'flex';
            }
        } else if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    }

    // 清理HTML内容，移除可能引起编辑器问题的特殊格式（当前已经是html，无需特殊处理）
    function sanitizeHtmlContent(html) {
        if (!html) return '';
        return html
    }

    // 根据sectionId在treeData中查找对应的text内容
    function findTextInTreeData(treeData, sectionId) {
        if (!treeData || !Array.isArray(treeData) || !sectionId) return null;

        // 遍历所有章节
        for (const chapter of treeData) {
            // 检查章节的children数组
            if (chapter.children && Array.isArray(chapter.children)) {
                // 在每个章节的子节点中查找匹配的sectionId
                const foundSection = chapter.children.find(
                    child => child.sectionId === sectionId
                );

                if (foundSection && foundSection.text) {
                    return foundSection.text;
                }
            }
        }

        return null;
    }

    // ==================== 页面数据 ====================
    let pageData = {
        documentId: null,
        nodeId: null,
        fullText: null,
        sections: [],
        isEditMode: false,
        // 编辑状态管理
        editStates: {
            left: false,   // 左侧编辑状态
            right: false   // 右侧编辑状态
        },
        // 存储编辑器实例
        editors: {
            original: [],  // 左侧原文编辑器
            diff: []       // 右侧AI润色编辑器
        }
    };

    // ==================== 核心功能 ====================
    // 获取文档ID从URL
    function getDocumentIdFromUrl() {
        const path = window.location.pathname;
        const match = path.match(/full-compare\/(\d+)/);
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

    // 处理sectionsData，兼容单节点、多节点和全量节点三种情况
    function processSectionsData(sectionsData) {
        let sections = [];

        if (!sectionsData) {
            console.error('sectionsData为空');
            return sections;
        }

        console.log('处理sectionsData:', sectionsData);
        console.log('is_full_document:', sectionsData.is_full_document);

        // 情况1：全量节点 (node_id = 'all')
        if (sectionsData.is_full_document === true && sectionsData.nodes) {
            console.log('全量节点模式，章节数量:', sectionsData.nodes.length);

            // 遍历所有章节
            sectionsData.nodes.forEach((chapter, chapterIndex) => {
                console.log(`章节 ${chapterIndex + 1}:`, chapter.nodeId, chapter.title);

                // 如果章节有子节点（小节），添加所有小节
                if (chapter.children && Array.isArray(chapter.children)) {
                    console.log(`章节 ${chapter.nodeId} 有 ${chapter.children.length} 个小节`);

                    chapter.children.forEach((child, childIndex) => {
                        sections.push({
                            ...child,
                            // 添加章节信息，方便显示
                            chapterNodeId: chapter.nodeId,
                            chapterTitle: chapter.title
                        });
                    });
                } else {
                    console.log(`章节 ${chapter.nodeId} 没有子节点`);
                    // 如果没有子节点，将章节本身作为一个节点
                    sections.push({
                        ...chapter,
                        chapterNodeId: chapter.nodeId,
                        chapterTitle: chapter.title
                    });
                }
            });

            console.log('全量节点处理后的小节总数:', sections.length);
        }
        // 情况2：特定节点 (node_id 为具体值)
        else if (sectionsData.node) {
            if (sectionsData.node.children && Array.isArray(sectionsData.node.children)) {
                // 多节点情况：有children数组（章节包含多个小节）
                console.log('多节点模式，小节数量:', sectionsData.node.children.length);
                sections = sectionsData.node.children.map(child => ({
                    ...child,
                    chapterNodeId: sectionsData.node.nodeId,
                    chapterTitle: sectionsData.node.title
                }));
            } else {
                // 单节点情况：node本身就是一个节点
                console.log('单节点模式');
                sections = [sectionsData.node];
            }
        } else {
            console.error('无法识别的数据格式:', sectionsData);
        }

        return sections;
    }
    let sourceForm = null
    // 在 full-compare 页面中获取参数
    async function loadPageData() {
        showLoading(true);
        try {
            const navParams = DataService.getNavigationParams();

            if (navParams) {
                const { documentId, nodeId, fullText, treeData ,source} = navParams;
                sourceForm = source
                currentSectionNodeId = nodeId || getNodeIdFromUrl();

                // 存储页面数据
                pageData.documentId = documentId;
                pageData.nodeId = nodeId;

                // 根据 </think> 进行分割，获取正文
                const startDelimiter = '</think>';
                if (fullText && fullText.includes(startDelimiter)){
                    pageData.fullText = fullText.split('</think>')[1];
                } else {
                    pageData.fullText = fullText;
                }

                console.log('文档ID:', documentId);
                console.log('节点ID:', nodeId);
                console.log('当前节点ID:', currentSectionNodeId);
                console.log('完整文本长度:', fullText ? fullText.length : 0);
                console.log('treeData:', treeData);

                // 获取章节内容数据
                const sectionsData = await DataService.getSectionContentOnly(documentId, nodeId);
                console.log('获取到章节数据:', sectionsData);

                // 处理章节数据，兼容单节点、多节点和全量节点
                const rawSections = processSectionsData(sectionsData);
                console.log('处理后的小节数量:', rawSections.length);

                if (rawSections.length > 0) {
                    // 处理左侧原文内容
                    pageData.sections = rawSections.map((section, index) => {
                        // 生成显示用的标题
                        let displayTitle = section.title || '';
                        // 如果是全量节点，并且有章节信息，可以显示更详细的标题
                        if (section.chapterTitle && section.chapterNodeId !== section.nodeId) {
                            displayTitle = `${section.chapterNodeId} ${section.chapterTitle} - ${section.nodeId} ${section.title}`;
                        }

                        // 确定右侧polishedContent的内容
                        let polishedContent = '';

                        // 如果treeData存在且长度大于0，使用treeData构建右侧内容
                        if (treeData && treeData.length > 0) {
                            // 查找匹配的sectionId
                            const foundText = findTextInTreeData(treeData, section.nodeId);
                            if (foundText) {
                                polishedContent = foundText;
                                console.log(`为节点 ${section.nodeId} 找到treeData中的内容，长度:`, foundText.length);
                            } else {
                                console.warn(`在treeData中未找到节点 ${section.nodeId} 的内容`);
                                // 如果treeData中找不到，则使用原有逻辑
                                polishedContent = pageData.fullText || section.content || '';
                            }
                        } else {
                            // 没有treeData，使用原有逻辑
                            polishedContent = pageData.fullText || section.content || '';
                        }

                        // 处理Markdown格式的内容
                        const originalContent = processEditorContent(section.content || '');
                        polishedContent = processEditorContent(polishedContent);

                        return {
                            id: section.nodeId || `section-${index + 1}`,
                            title: section.title || '',
                            displayTitle: displayTitle,
                            originalContent: originalContent,
                            polishedContent: polishedContent,
                            level: section.level || 2,
                            status: section.status || 'writing',
                            reviewScore: section.reviewScore,
                            keyPoint: section.keyPoint || '',
                            // 章节信息（用于全量节点）
                            chapterNodeId: section.chapterNodeId,
                            chapterTitle: section.chapterTitle,
                            // 编辑器实例
                            originalEditor: null,
                            diffEditor: null
                        };
                    });

                    console.log('处理后的小节数据:', pageData.sections);

                    // 更新页面UI
                    updatePageUI();

                    // 动态创建编辑器容器
                    createEditorContainers();

                    // 初始化编辑器
                    await initializeEditors();
                } else {
                    console.error('没有获取到小节数据');
                    flash('未找到小节内容', 'error');
                }
            } else {
                // 处理没有参数的情况
                console.error('未找到导航参数');
                flash('页面参数错误，请重新操作', 'error');
                // 3秒后返回上一页
                setTimeout(() => {
                    history.back();
                }, 3000);
            }
        } catch (error) {
            console.error('加载页面数据失败:', error);
            flash('加载数据失败: ' + error.message, 'error');
        } finally {
            showLoading(false);
        }
    }

    // 动态创建编辑器容器
    function createEditorContainers() {
        const sections = pageData.sections;
        if (!sections || sections.length === 0) return;

        // 左侧原文列
        const originalColumn = document.querySelector('.original-column');
        // 右侧AI润色列
        const comparisonColumn = document.querySelector('.comparison-column');

        // 清空现有内容
        originalColumn.innerHTML = '';
        comparisonColumn.innerHTML = '';

        // 为每个小节创建编辑器容器
        for (let index = 0; index < sections.length; index++) {
            const section = sections[index];
            const sectionId = section.id || `section-${index + 1}`;
            const safeId = sectionId.replace(/[\.\s]/g, '_');

            // 左侧原文编辑器容器
            const originalCard = createEditorCard(section, index, 'original', safeId);
            originalColumn.appendChild(originalCard);

            // 右侧AI润色编辑器容器
            const comparisonCard = createEditorCard(section, index, 'diff', safeId);
            comparisonColumn.appendChild(comparisonCard);
        }
    }

    // 创建编辑器卡片
    function createEditorCard(section, index, prefix, safeId) {
        const card = document.createElement('div');
        card.className = `flex-col comparison-card ${index > 0 ? 'comparison-card-gap' : ''}`;

        // 使用displayTitle，如果没有则使用title
        const cardTitle = section.displayTitle || `${section.id} ${section.title}`;

        card.innerHTML = `
            <div class="flex-col">
                <div class="flex-col justify-start items-center relative panel-header">
                    <img class="shrink-0 panel-header-bg" src="/static/project_document/images/full-compare/illustration-doc.png" />
                    <span class="panel-label card-title-position">${cardTitle}</span>
                </div>
                <div class="flex-col justify-start diff-image-wrapper">
                    <div class="writing-toolbar">
                        <div id="${prefix}-toolbar-${safeId}"></div>
                    </div>
                    <div id="${prefix}-editor-${safeId}" class="diff-editor"></div>
                </div>
            </div>
        `;

        return card;
    }

    // 更新页面UI
    function updatePageUI() {
        // 更新左侧原文面板
        updateOriginalPanel();

        // 更新右侧AI润色面板
        updateComparisonPanel();

        // 更新编辑面板的标题
        updateEditPanelTitles();
    }

    // 更新左侧原文面板
    function updateOriginalPanel() {
        const originalPanel = document.querySelector('.original-panel-view .panel-body');
        if (!originalPanel || pageData.sections.length === 0) return;

        // 清空原有内容
        originalPanel.innerHTML = '';

        // 添加每个小节的内容
        pageData.sections.forEach((section, index) => {
            // 创建小节标题行
            const sectionHeader = document.createElement('div');
            sectionHeader.className = 'flex-row items-baseline section-header-row' +
                (index === 0 ? ' section-header-first' : '');

            const sectionNumber = document.createElement('span');
            sectionNumber.className = 'section-number section-number-gradient';
            sectionNumber.textContent = section.id;

            const sectionHeading = document.createElement('span');
            sectionHeading.className = 'ml-16 section-heading';
            // 使用displayTitle，如果没有则使用title
            sectionHeading.textContent = section.displayTitle || section.title;

            sectionHeader.appendChild(sectionNumber);
            sectionHeader.appendChild(sectionHeading);

            // 创建小节内容容器 - 修复：使用div而不是span，并设置innerHTML
            const sectionContent = document.createElement('div');
            sectionContent.className = 'summary-text summary-paragraph preview-content';

            // 使用innerHTML而不是textContent，以正确显示HTML格式
            const content = section.originalContent || '（暂无内容）';
            sectionContent.innerHTML = content;

            // 添加到面板
            originalPanel.appendChild(sectionHeader);
            originalPanel.appendChild(sectionContent);
        });
    }

    // 更新右侧AI润色面板
    function updateComparisonPanel() {
        const comparisonPanel = document.querySelector('.comparison-panel-view .panel-body');
        if (!comparisonPanel || pageData.sections.length === 0) return;

        // 清空原有内容
        comparisonPanel.innerHTML = '';

        // 添加每个小节的内容
        pageData.sections.forEach((section, index) => {
            // 创建小节标题行
            const sectionHeader = document.createElement('div');
            sectionHeader.className = 'flex-row items-baseline section-header-row' +
                (index === 0 ? ' section-header-first' : '');

            const sectionNumber = document.createElement('span');
            sectionNumber.className = 'section-number section-number-gradient';
            sectionNumber.textContent = section.id;

            const sectionHeading = document.createElement('span');
            sectionHeading.className = 'ml-16 section-heading';
            // 使用displayTitle，如果没有则使用title
            sectionHeading.textContent = section.displayTitle || section.title;

            sectionHeader.appendChild(sectionNumber);
            sectionHeader.appendChild(sectionHeading);

            // 创建小节内容容器 - 修复：使用div而不是span，并设置innerHTML
            const sectionContent = document.createElement('div');
            sectionContent.className = 'summary-text summary-paragraph preview-content';

            // 使用innerHTML而不是textContent，以正确显示HTML格式
            const content = section.polishedContent || '（暂无内容）';
            sectionContent.innerHTML = content;

            // 添加到面板
            comparisonPanel.appendChild(sectionHeader);
            comparisonPanel.appendChild(sectionContent);
        });
    }

    // 更新编辑面板的标题
    function updateEditPanelTitles() {
        // 更新左侧编辑面板的标题
        const originalEditHeaders = document.querySelectorAll('.original-column .card-title-position');
        originalEditHeaders.forEach((header, index) => {
            if (pageData.sections[index]) {
                const section = pageData.sections[index];
                const cardTitle = section.displayTitle || `${section.id} ${section.title}`;
                header.textContent = cardTitle;
            }
        });

        // 更新右侧编辑面板的标题
        const comparisonEditHeaders = document.querySelectorAll('.comparison-column .card-title-position');
        comparisonEditHeaders.forEach((header, index) => {
            if (pageData.sections[index]) {
                const section = pageData.sections[index];
                const cardTitle = section.displayTitle || `${section.id} ${section.title}`;
                header.textContent = cardTitle;
            }
        });
    }

    // 初始化编辑器
    async function initializeEditors() {
        // 初始化左侧原文编辑器
        await initSectionEditors('original', 'originalContent');

        // 初始化右侧AI润色编辑器
        await initSectionEditors('diff', 'polishedContent');
    }

    // 初始化小节编辑器（修改了uploadImage配置）
    async function initSectionEditors(prefix, contentField) {
        const sections = pageData.sections;
        if (!sections || sections.length === 0) return;

        for (let index = 0; index < sections.length; index++) {
            const section = sections[index];
            const sectionId = section.id || `section-${index + 1}`;
            const safeId = sectionId.replace(/[\.\s]/g, '_');

            const editorContainer = document.getElementById(`${prefix}-editor-${safeId}`);
            const toolbarContainer = document.getElementById(`${prefix}-toolbar-${safeId}`);

            if (!editorContainer || !toolbarContainer) {
                console.warn(`编辑器容器未找到: ${prefix}-editor-${safeId} 或 ${prefix}-toolbar-${safeId}`);
                return;
            }

            // 如果编辑器已经存在，跳过初始化
            if (section[`${prefix}Editor`]) {
                console.log(`编辑器已存在，跳过: ${prefix}-editor-${safeId}`);
                return;
            }

            let content = section[contentField] || '';

            // 清理HTML内容，移除可能引起编辑器问题的特殊格式
            const sanitizedContent = sanitizeHtmlContent(content);

            // 如果wangEditor可用，使用富文本编辑器
            if (window.TiptapEditorFactory) {
                try {
                    // 清空容器
                    editorContainer.innerHTML = '';

                    // 创建 Tiptap 编辑器
                    const editor = await window.TiptapEditorFactory.createEditor({
                        selector: `#${prefix}-editor-${safeId}`,
                        toolbarSelector: `#${prefix}-toolbar-${safeId}`
                    });
                    editor.setHtml(sanitizedContent || '<p></p>');

                    // 存储编辑器实例
                    section[`${prefix}Editor`] = editor;
                    pageData.editors[prefix][index] = editor;

                    console.log(`成功初始化编辑器: ${prefix}-editor-${safeId}`);
                } catch (e) {
                    console.error('富文本初始化失败', e);
                    // 如果富文本初始化失败，使用纯文本显示
                    editorContainer.innerHTML = sanitizedContent || '<p>（暂无内容）</p>';
                    flash('编辑器初始化失败，已切换到纯文本模式', 'error');
                }
            } else {
                // 如果没有富文本编辑器，直接显示内容
                editorContainer.innerHTML = sanitizedContent || '<p>（暂无内容）</p>';
            }
        }
    }

    // 同步编辑器内容到数据模型（重要：在切换状态和保存时调用）
    function syncEditorContentToData() {
        const sections = pageData.sections;
        if (!sections || sections.length === 0) return;

        for (let index = 0; index < sections.length; index++) {
            const section = sections[index];
            const sectionId = section.id || `section-${index + 1}`;
            const safeId = sectionId.replace(/[\.\s]/g, '_');

            // 同步左侧编辑器内容到originalContent
            if (pageData.editStates.left) {
                // 如果在编辑状态，从编辑器获取
                const originalEditor = section.originalEditor;
                if (originalEditor && typeof originalEditor.getHtml === 'function') {
                    const content = originalEditor.getHtml();
                    if (content && content !== '<p><br></p>' && content !== '<p></p>') {
                        section.originalContent = content;
                    }
                } else {
                    // 如果在浏览状态，从DOM获取
                    const editorContainer = document.getElementById(`original-editor-${safeId}`);
                    if (editorContainer) {
                        section.originalContent = editorContainer.innerHTML;
                    }
                }
            }

            // 同步右侧编辑器内容到polishedContent
            if (pageData.editStates.right) {
                // 如果在编辑状态，从编辑器获取
                const diffEditor = section.diffEditor;
                if (diffEditor && typeof diffEditor.getHtml === 'function') {
                    const content = diffEditor.getHtml();
                    if (content && content !== '<p><br></p>' && content !== '<p></p>') {
                        section.polishedContent = content;
                    }
                } else {
                    // 如果在浏览状态，从DOM获取
                    const editorContainer = document.getElementById(`diff-editor-${safeId}`);
                    if (editorContainer) {
                        section.polishedContent = editorContainer.innerHTML;
                    }
                }
            }
        }
    }

    // 获取编辑器内容数组（新增：返回每个小节的内容数组）
    function getEditorContentsArray(prefix) {
        const sections = pageData.sections;
        if (!sections || sections.length === 0) return [];

        const contents = [];

        for (let index = 0; index < sections.length; index++) {
            const section = sections[index];
            let content = '';

            if (prefix === 'original') {
                // 左侧内容
                if (pageData.editStates.left) {
                    // 编辑状态：从编辑器获取
                    const editor = section.originalEditor;
                    if (editor && typeof editor.getHtml === 'function') {
                        content = editor.getHtml();
                    } else {
                        const sectionId = section.id || `section-${index + 1}`;
                        const safeId = sectionId.replace(/[\.\s]/g, '_');
                        const editorContainer = document.getElementById(`original-editor-${safeId}`);
                        content = editorContainer ? editorContainer.innerHTML : '';
                    }
                } else {
                    // 浏览状态：从数据模型获取
                    content = section.originalContent || '';
                }
            } else if (prefix === 'diff') {
                // 右侧内容
                if (pageData.editStates.right) {
                    // 编辑状态：从编辑器获取
                    const editor = section.diffEditor;
                    if (editor && typeof editor.getHtml === 'function') {
                        content = editor.getHtml();
                    } else {
                        const sectionId = section.id || `section-${index + 1}`;
                        const safeId = sectionId.replace(/[\.\s]/g, '_');
                        const editorContainer = document.getElementById(`diff-editor-${safeId}`);
                        content = editorContainer ? editorContainer.innerHTML : '';
                    }
                } else {
                    // 浏览状态：从数据模型获取
                    content = section.polishedContent || '';
                }
            }

            // 如果内容为空，使用默认值
            if (!content || content === '<p><br></p>' || content === '<p></p>') {
                if (prefix === 'original') {
                    content = section.originalContent || '';
                } else if (prefix === 'diff') {
                    content = section.polishedContent || '';
                }
            }

            // 处理内容中的Markdown
            content = processEditorContent(content);

            contents.push(content || '');
        }

        return contents;
    }

    // 更新浏览状态的显示内容（从数据模型更新）
    function updateViewPanels() {
        if (!pageData.editStates.left && !pageData.editStates.right) {
            // 如果都不在编辑状态，更新浏览面板
            updateOriginalPanel();
            updateComparisonPanel();
        }
    }

    // ==================== 事件绑定 ====================
    // 页面元素
    const pageEl = document.querySelector('.page');
    const editBtn = document.getElementById('compare-edit-btn');
    const editIcons = document.querySelectorAll('.edit-icon');
    const backLink = document.querySelector('.header-bar .header-link');

    // 返回写作按钮事件
    if (backLink) {
        backLink.style.cursor = 'pointer';
        backLink.parentElement.style.cursor = 'pointer';
        backLink.parentElement.addEventListener('click', () => {
            const documentId = pageData.documentId || getDocumentIdFromUrl();
            if (documentId && currentSectionNodeId) {
                window.location.href = `/project_document/writing-workspace/${documentId}?node_id=${currentSectionNodeId}`;
            } else if (documentId) {
                window.location.href = `/project_document/writing-workspace/${documentId}`;
            } else {
                window.location.href = '../writing-workspace/index.html';
            }
        });
    }

    // 设置编辑模式
    async function setEditMode(side, enabled) {
        if (!pageEl) return;

        // 重要：退出编辑状态时，同步编辑器内容到数据模型
        if (!enabled && pageData.editStates[side]) {
            syncEditorContentToData();
            // 更新浏览状态显示
            updateViewPanels();
        }

        // 更新编辑状态
        pageData.editStates[side] = enabled;

        if (side === 'left') {
            pageEl.classList.toggle('compare-edit-left', enabled);
        } else {
            pageEl.classList.toggle('compare-edit-mode', enabled);
        }

        if (editBtn && side === 'right') {
            editBtn.classList.toggle('active', enabled);
        }

        if (enabled) {
            // 进入编辑模式时，初始化对应侧的编辑器
            if (side === 'left') {
                await initSectionEditors('original', 'originalContent');
            } else if (side === 'right') {
                await initSectionEditors('diff', 'polishedContent');
            }
        } else {
            // 退出编辑模式时，更新浏览状态显示
            updateViewPanels();
        }
    }

    // 切换编辑模式
    async function toggleEditMode(side) {
        const className = side === 'left' ? 'compare-edit-left' : 'compare-edit-mode';
        const next = pageEl ? !pageEl.classList.contains(className) : true;
        await setEditMode(side, next);
    }

    // 编辑按钮事件
    if (editBtn) {
        editBtn.addEventListener('click', async function () {
            await toggleEditMode('right');
        });
    }

    // 编辑图标事件
    if (editIcons && editIcons.length) {
        editIcons.forEach(function (icon) {
            icon.addEventListener('click', async function (event) {
                if (event && typeof event.stopPropagation === 'function') {
                    event.stopPropagation();
                }
                if (event && typeof event.preventDefault === 'function') {
                    event.preventDefault();
                }
                const side = icon.getAttribute('data-side') === 'left' ? 'left' : 'right';
                await toggleEditMode(side);
            });
        });
    }

    // ==================== 替换功能 ====================
    // 替换确认相关元素
    const replaceConfirmOverlay = document.getElementById('replace-confirm-overlay');
    const replaceConfirmTitle = document.getElementById('replace-confirm-title');
    const replaceConfirmCancel = document.getElementById('replace-confirm-cancel');
    const replaceConfirmConfirm = document.getElementById('replace-confirm-confirm');
    let pendingReplaceAction = '';
    let pendingReplaceLabel = '';

    // 获取替换标题
    function getReplaceTitle(action) {
        if (action === 'use-left') return '确定按左框内容替换吗？';
        if (action === 'use-right') return '确定按右框内容替换吗？';
        return '确定替换吗？';
    }

    // 关闭替换确认对话框
    function closeReplaceConfirm() {
        if (replaceConfirmOverlay) {
            replaceConfirmOverlay.classList.remove('show');
        }
        pendingReplaceAction = '';
        pendingReplaceLabel = '';
    }

    // 打开替换确认对话框
    function openReplaceConfirm(action, label) {
        pendingReplaceAction = action;
        pendingReplaceLabel = label;
        if (replaceConfirmTitle) {
            replaceConfirmTitle.textContent = getReplaceTitle(action);
        }
        if (replaceConfirmOverlay) {
            replaceConfirmOverlay.classList.add('show');
        }
    }

    // 执行替换操作（修复版：保存所有小节内容）
    async function applyAction(action, label) {
        showLoading(true);
        try {
            if (!pageData.documentId) {
                flash('文档信息不完整', 'error');
                return;
            }

            // 重要：在保存前同步编辑器内容到数据模型
            syncEditorContentToData();

            let contentsToSave = [];
            if (action === 'use-left') {
                // 使用左侧所有小节的内容（无论编辑还是浏览状态）
                contentsToSave = getEditorContentsArray('original');
                console.log('使用左侧内容:', contentsToSave);
            } else if (action === 'use-right') {
                // 使用右侧所有小节的内容（无论编辑还是浏览状态）
                contentsToSave = getEditorContentsArray('diff');
                console.log('使用右侧内容:', contentsToSave);
            } else if (action === 'discard') {
                // 放弃替换，返回写作页面
                const documentId = pageData.documentId || getDocumentIdFromUrl();
                if (documentId && currentSectionNodeId) {
                    window.location.href = `/project_document/writing-workspace/${documentId}?node_id=${currentSectionNodeId}`;
                } else if (documentId) {
                    window.location.href = `/project_document/writing-workspace/${documentId}`;
                } else {
                    window.location.href = '../writing-workspace/index.html';
                }
                return;
            }

            // 检查是否有内容
            if (contentsToSave.length === 0 || contentsToSave.every(content => !content || content.trim() === '')) {
                flash('没有获取到可保存的内容', 'error');
                showLoading(false);
                return;
            }

            // 保存每个小节的内容到服务器
            const savePromises = pageData.sections.map((section, index) => {
                if (index < contentsToSave.length && contentsToSave[index]) {
                    // 使用小节节点ID，如果没有则使用文档节点ID
                    const nodeIdToSave = section.id || pageData.nodeId;
                    if (!nodeIdToSave) {
                        console.error('无法确定要保存的节点ID');
                        return Promise.resolve();
                    }

                    return DataService.saveSectionContent(
                        pageData.documentId,
                        nodeIdToSave,
                        {
                            content: contentsToSave[index]
                        }
                    ).then(result => {
                        console.log(`保存第${index + 1}个小节成功:`, result);
                        return result;
                    }).catch(error => {
                        console.error(`保存第${index + 1}个小节失败:`, error);
                        throw error;
                    });
                }
                return Promise.resolve();
            });

            // 等待所有保存操作完成
            await Promise.all(savePromises);

            flash(`已选择：${label}`, 'success');

            // 延迟返回写作页面，让用户看到成功提示
            setTimeout(() => {
                const documentId = pageData.documentId || getDocumentIdFromUrl();
                if(sourceForm==='polish'){
                    if (documentId) {
                        window.location.href = `/project_document/preview-review/${documentId}?mode=editable`;
                    }
                    else{
                         window.location.href = '../writing-workspace/index.html';
                    }
                }
                else if(sourceForm==='heuristic'){
                     if (documentId && currentSectionNodeId) {
                        window.location.href = `/project_document/writing-workspace/${documentId}?node_id=${currentSectionNodeId}`;
                    }
                    else{
                         window.location.href = '../writing-workspace/index.html';
                    }
                }
                else{
                    if (documentId && currentSectionNodeId) {
                        window.location.href = `/project_document/writing-workspace/${documentId}?node_id=${currentSectionNodeId}`;
                    } else if (documentId) {
                        window.location.href = `/project_document/writing-workspace/${documentId}`;
                    } else {
                        window.location.href = '../writing-workspace/index.html';
                    }
                }
            }, 1000);

        } catch (error) {
            console.error('保存内容失败:', error);
            flash('保存失败: ' + error.message, 'error');
        } finally {
            showLoading(false);
        }
    }

    // ==================== 按钮事件绑定 ====================
    // 按钮点击事件
    const actionButtons = document.querySelectorAll('.action-button');
    actionButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            btn.blur();
            const label = btn.querySelector('.action-label') ?
                          btn.querySelector('.action-label').textContent.trim() :
                          btn.textContent.trim();
            const action = btn.getAttribute('data-action') || label;

            console.log('按钮点击:', action, label);

            if (action === 'use-left' || action === 'use-right') {
                openReplaceConfirm(action, label);
                return;
            }
            // 放弃替换直接执行
            applyAction(action, label);
        });
    });

    // 替换确认对话框事件
    if (replaceConfirmCancel) {
        replaceConfirmCancel.addEventListener('click', closeReplaceConfirm);
    }

    if (replaceConfirmConfirm) {
        replaceConfirmConfirm.addEventListener('click', function () {
            if (!pendingReplaceAction) {
                closeReplaceConfirm();
                return;
            }
            applyAction(pendingReplaceAction, pendingReplaceLabel || pendingReplaceAction);
            closeReplaceConfirm();
        });
    }

    if (replaceConfirmOverlay) {
        replaceConfirmOverlay.addEventListener('click', function (e) {
            if (e.target === replaceConfirmOverlay) {
                closeReplaceConfirm();
            }
        });
    }

    // ==================== 页面初始化 ====================
    // 立即调用 loadPageData
    loadPageData().catch(error => {
        console.error('加载页面数据失败:', error);
        flash('加载页面数据失败: ' + error.message, 'error');
    });
});