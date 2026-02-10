// outline-confirm/index.js
document.addEventListener('DOMContentLoaded', () => {
  // Toast提示函数
  const flash = (text, type = 'info') => {
    const hint = document.createElement('div');
    hint.className = `toast-hint toast-${type}`;
    hint.innerText = text;
    document.body.appendChild(hint);
    setTimeout(() => hint.classList.add('show'), 10);
    setTimeout(() => {
      hint.classList.remove('show');
      setTimeout(() => hint.remove(), 200);
    }, 3000);
  };

  // 显示/隐藏加载状态
  const showLoading = () => {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
      loadingOverlay.style.display = 'flex';
    }
  };

  const hideLoading = () => {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (loadingOverlay) {
      loadingOverlay.style.display = 'none';
    }
  };

  // 获取CSRF token
  const getCSRFToken = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };

  // 从URL路径中提取document_id
  const getDocumentIdFromUrl = () => {
    const pathParts = window.location.pathname.split('/');
    const lastPart = pathParts[pathParts.length - 1];
    return parseInt(lastPart, 10);
  };

  // 获取文档ID（优先使用全局变量，其次从URL提取）
  const getDocumentId = () => {
    if (typeof DOCUMENT_ID !== 'undefined' && DOCUMENT_ID) {
      return DOCUMENT_ID;
    }
    return getDocumentIdFromUrl();
  };

  // 获取完整文档数据
  const fetchDocumentData = async (documentId) => {
    try {
      const response = await fetch(`/project_document/${documentId}`, {
        method: 'GET',
        headers: {
          'X-CSRF-Token': getCSRFToken()
        }
      });

      const result = await response.json();

      if (result.code === 200) {
        return result.data;
      } else {
        throw new Error(result.message || '获取文档数据失败');
      }
    } catch (error) {
      console.error('获取文档数据失败:', error);
      throw error;
    }
  };

  // 解析doc_guide字符串为JSON对象
  const parseDocGuide = (docGuideString) => {
    if (!docGuideString) return [];

    try {
      // 将单引号替换为双引号，然后解析JSON
      const jsonString = docGuideString.replace(/'/g, '"');
      return JSON.parse(jsonString);
    } catch (error) {
      console.error('解析doc_guide失败:', error);
      // 尝试其他解析方式
      try {
        // 如果已经是JSON格式，直接解析
        return JSON.parse(docGuideString);
      } catch (e) {
        console.error('直接解析doc_guide也失败:', e);
        return [];
      }
    }
  };

  // 从文档数据中提取5W要点（基于doc_guide）
  const extractOverviewData = (documentData) => {
    // 解析doc_guide
    if (documentData.doc_guide) {
        return documentData.doc_guide  // 直接返回字符串格式——全文要点
    }

    const guideItems = parseDocGuide(documentData.doc_guide);

    if (!guideItems || guideItems.length === 0) {
      // 如果doc_guide为空，返回默认数据
      const overview = [];

      // 1. What - 项目是什么
      if (documentData.title) {
        overview.push({
          key: 'what',
          label: 'What',
          content: documentData.title
        });
      }

      // 2. Why - 项目背景/原因
      if (documentData.idea) {
        overview.push({
          key: 'why',
          label: 'Why',
          content: documentData.idea.substring(0, 100) + (documentData.idea.length > 100 ? '...' : '')
        });
      }

      // 3. Who - 目标用户/利益相关者
      if (documentData.industry) {
        overview.push({
          key: 'who',
          label: 'Who',
          content: `目标用户：${documentData.industry}行业用户`
        });
      }

      // 4. When - 时间规划
      overview.push({
        key: 'when',
        label: 'When',
        content: '根据项目周期制定详细时间规划'
      });

      // 5. Where - 实施范围/场景
      if (documentData.doc_guide) {
        overview.push({
          key: 'where',
          label: 'Where',
          content: documentData.doc_guide.substring(0, 100) + (documentData.doc_guide.length > 100 ? '...' : '')
        });
      }

      return overview;
    }

    // 使用doc_guide数据生成overview
    return guideItems.map((item, index) => {
      // 为每个item分配一个key，可以使用预设的keys或自定义
      const presetKeys = ['what', 'why', 'who', 'when', 'where'];
      const key = presetKeys[index] || `item_${index}`;
      const label = item.keyword || `要点${index + 1}`;
      const content = item.content || '暂无内容';

      return {
        key,
        label,
        content
      };
    });
  };

  // 从文档数据中提取章节数据
  const extractChaptersData = (documentData) => {
    if (!documentData.outline || !Array.isArray(documentData.outline)) {
      return [];
    }

    return documentData.outline.map(chapter => {
      // 处理章节内容
      const sections = [];

      // 如果有子节点，添加到sections
      if (chapter.children && Array.isArray(chapter.children)) {
        chapter.children.forEach(child => {
          if (child.title) {
            // 添加node_id到小节标题
            const sectionTitle = child.node_id ? `${child.node_id} ${child.title}` : child.title;
            sections.push(sectionTitle);
          }
        });
      }

      return {
        title: chapter.title || '未命名章节',
        nodeId: chapter.node_id || '', // 保存node_id
        point: chapter.key_point || '暂无写作要点',
        sections: sections.length > 0 ? sections : ['暂无小节内容']
      };
    });
  };

  // 创建5W要点项目组件
  const createOverviewItem = (item, isLast) => {
    const contentClass = isLast ? 'self-stretch section-content' : 'self-start section-content';
    return `
      <span class="self-start section-label section-label--${item.key}">${item.label}</span>
      <span class="${contentClass}">${item.content}</span>
    `;
  };

  // 渲染5W要点内容
  const renderOverview = (data) => {
    const container = document.getElementById('overview-content');
    const loadingEl = document.getElementById('overview-loading');

    if (loadingEl) {
      loadingEl.remove();
    }

    if (container) {
      if (data.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无全文要点数据</div>';
      } else {
        container.innerHTML = data;
      }
    }
  };

  // 创建章节卡片组件
  const createChapterCard = (chapter, index) => {
    const sectionsHtml = chapter.sections.map(s => `<span class="chapter-section">${s}<br /></span>`).join('');

    // 在章节标题中显示node_id
    const chapterTitle = chapter.nodeId ? `${chapter.nodeId} ${chapter.title}` : chapter.title;

    return `
      <div class="flex-col chapter-card" data-chapter-index="${index}">
        <div class="flex-col justify-start items-start relative card-header">
          <img class="shrink-0 card-header-bg" src="/static/project_document/images/common/bg-card-header.png" />
          <span class="card-title">${chapterTitle}</span>
        </div>
        <div class="chapter-content">
          <span class="chapter-point" style="display:none">${chapter.point}<br /></span>
          <span class="chapter-section"><br /></span>
          ${sectionsHtml}
        </div>
      </div>
    `;
  };

  // 渲染章节列表
  const renderChapters = (data) => {
    const container = document.getElementById('chapters-container');
    const loadingEl = document.getElementById('chapters-loading');

    if (loadingEl) {
      loadingEl.remove();
    }

    if (container) {
      if (data.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无章节数据</div>';
      } else {
        container.innerHTML = data.map(createChapterCard).join('');
      }
    }
  };

  // 初始化页面数据
  const initPageData = async () => {
    const documentId = getDocumentId();

    if (!documentId || isNaN(documentId)) {
      flash('文档ID无效，请返回重新操作', 'error');
      return;
    }

    showLoading();

    try {
      // 获取文档数据
      const documentData = await fetchDocumentData(documentId);

      // 提取并渲染5W要点（基于doc_guide）
      const overviewData = extractOverviewData(documentData);
      renderOverview(overviewData);

      // 提取并渲染章节数据
      const chaptersData = extractChaptersData(documentData);
      renderChapters(chaptersData);

      flash('数据加载成功', 'success');

    } catch (error) {
      console.error('初始化页面数据失败:', error);
      flash(`数据加载失败: ${error.message}`, 'error');

      // 显示错误状态
      renderOverview([]);
      renderChapters([]);
    } finally {
      hideLoading();
    }
  };

  // 初始化页面功能
  const initPageFunctionality = () => {
    const documentId = getDocumentId();

    // 返回按钮
    const backLink = document.getElementById('back-link');
    if (backLink) {
      backLink.addEventListener('click', () => {
        window.location.href = `/project_document/outline-draft`;
      });
    }

    // 上一步按钮
    const prevButton = document.getElementById('prev-button');
    if (prevButton) {
      prevButton.addEventListener('click', () => {
        window.location.href = `/project_document/outline-draft`;
      });
    }

    // 下一步按钮（继续写作）
    const nextButton = document.getElementById('next-button');
    if (nextButton) {
      nextButton.addEventListener('click', () => {
        if (documentId) {
          // 保存到localStorage
          localStorage.setItem('current_document_id', documentId);
          // 跳转到写作工作区
          window.location.href = `/project_document/writing-workspace/${documentId}`;
        } else {
          flash('无法跳转，缺少文档ID', 'error');
        }
      });
    }

    // 初始化步骤条
    const stepsContainer = document.getElementById('steps-container');
    if (stepsContainer) {
      const routes = {
        1: '/project_document/outline-draft',
        2: null,
        3: documentId ? `/project_document/writing-workspace/${documentId}` : '#',
        4: documentId ? `/project_document/preview-review?mode=editable&document_id=${documentId}` : '#',
      };

      // 假设StepsComponent已定义
      if (typeof StepsComponent !== 'undefined') {
        StepsComponent.mount(stepsContainer, {
          active: 2,
          routes: routes,
          onCurrent: () => flash('当前已在确认大纲页面'),
        });
      }
    }
  };

  // 生成二级章节写作要点
  const generateLevelTwoKeypoints = async (nodeId) => {
    const documentId = getDocumentId();

    if (!documentId || !nodeId) {
      flash('参数不完整，无法生成写作要点', 'error');
      return null;
    }

    try {
      const response = await fetch(`/project_document/outline/${documentId}/level-two-keypoints`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCSRFToken()
        },
        body: JSON.stringify({
          node_id: nodeId
        })
      });

      const result = await response.json();

      if (result.code === 200) {
        return result.data;
      } else {
        throw new Error(result.message || '生成写作要点失败');
      }
    } catch (error) {
      console.error('生成二级章节写作要点失败:', error);
      throw error;
    }
  };

  // 为章节卡片添加点击事件（生成二级写作要点）
  const initChapterCardInteractions = () => {
    // 使用事件委托处理章节卡片点击
    const chaptersContainer = document.getElementById('chapters-container');

    if (chaptersContainer) {
      chaptersContainer.addEventListener('click', async (event) => {
        const chapterCard = event.target.closest('.chapter-card');

        if (chapterCard) {
          const chapterIndex = chapterCard.dataset.chapterIndex;
          // 这里需要根据实际的节点ID来调用
          // 暂时只显示提示
          flash(`点击了第${parseInt(chapterIndex) + 1}个章节`, 'info');
        }
      });
    }
  };

  // 初始化页面
  const init = async () => {
    try {
      // 初始化页面数据
      await initPageData();

      // 初始化页面功能
      initPageFunctionality();

      // 初始化章节卡片交互
      initChapterCardInteractions();

    } catch (error) {
      console.error('页面初始化失败:', error);
      flash('页面初始化失败，请刷新重试', 'error');
    }
  };

  // 启动初始化
  init();
});