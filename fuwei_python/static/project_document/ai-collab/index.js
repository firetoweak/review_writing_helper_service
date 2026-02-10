document.addEventListener('DOMContentLoaded', () => {
  const go = (path) => {
    window.location.href = path;
  };

  let originalEditor = null;
  let aiEditor = null;

  // 从localStorage读取对比数据
  const comparisonDataStr = localStorage.getItem('ai-writing-comparison');
  if (comparisonDataStr) {
    try {
      const comparisonData = JSON.parse(comparisonDataStr);
      
      // 更新页面内容
      const originalContent = document.getElementById('original-content');
      const aiContent = document.getElementById('ai-content');
      const sectionTitles = document.querySelectorAll('.section-title.section-title-gradient');
      
      if (originalContent && comparisonData.originalText) {
        originalContent.innerHTML = `<span class="content-text content-justify">${comparisonData.originalText}</span>`;
      }
      
      if (aiContent && comparisonData.aiGeneratedText) {
        aiContent.innerHTML = `<span class="content-text content-justify">${comparisonData.aiGeneratedText}</span>`;
      }
      
      if (sectionTitles.length >= 2 && comparisonData.sectionTitle) {
        sectionTitles[0].textContent = comparisonData.sectionTitle;
        sectionTitles[1].textContent = comparisonData.sectionTitle;
      }
    } catch (e) {
      console.error('解析对比数据失败:', e);
    }
  }

  // 初始化原文编辑器
  const initOriginalEditor = () => {
    console.log('初始化原文编辑器...');
    
    if (!window.wangEditor) {
      console.error('wangEditor 未加载');
      alert('编辑器库未加载，请刷新页面重试');
      return;
    }
    
    if (originalEditor) {
      console.log('原文编辑器已存在');
      return;
    }
    
    const { createEditor, createToolbar } = window.wangEditor;
    const originalContent = document.getElementById('original-content');
    const toolbarWrapper = document.getElementById('original-toolbar-wrapper');
    const section = originalContent.closest('.original-card');
    
    if (!originalContent) {
      console.error('找不到原文内容容器');
      return;
    }
    
    console.log('开始创建原文编辑器...');
    
    // 获取当前内容的纯文本
    const currentText = originalContent.innerText || originalContent.textContent || '';
    
    // 清空容器（wangEditor需要在空容器上初始化）
    originalContent.innerHTML = '';
    
    // 显示工具栏
    toolbarWrapper.style.display = 'block';
    toolbarWrapper.classList.add('show');
    
    // 添加编辑模式样式
    originalContent.classList.add('editing');
    if (section) section.classList.add('editing-mode');
    
    try {
      // 创建编辑器
      originalEditor = createEditor({
        selector: '#original-content',
        html: `<p>${currentText}</p>`,
        config: {
          placeholder: '请输入内容',
          hoverbarKeys: {
            text: { menuKeys: [] },
          },
        },
        mode: 'default',
      });
      
      console.log('原文编辑器创建成功');
      
      // 创建工具栏
      createToolbar({
        editor: originalEditor,
        selector: '#original-toolbar',
        mode: 'default',
      });
      
      console.log('原文工具栏创建成功');
    } catch (error) {
      console.error('创建原文编辑器失败:', error);
      alert('创建编辑器失败: ' + error.message);
    }
  };

  // 初始化AI内容编辑器
  const initAiEditor = () => {
    console.log('初始化AI编辑器...');
    
    if (!window.wangEditor) {
      console.error('wangEditor 未加载');
      alert('编辑器库未加载，请刷新页面重试');
      return;
    }
    
    if (aiEditor) {
      console.log('AI编辑器已存在');
      return;
    }
    
    const { createEditor, createToolbar } = window.wangEditor;
    const aiContent = document.getElementById('ai-content');
    const toolbarWrapper = document.getElementById('ai-toolbar-wrapper');
    const section = aiContent.closest('.ai-card');
    
    if (!aiContent) {
      console.error('找不到AI内容容器');
      return;
    }
    
    console.log('开始创建AI编辑器...');
    
    // 获取当前内容的纯文本
    const currentText = aiContent.innerText || aiContent.textContent || '';
    
    // 清空容器（wangEditor需要在空容器上初始化）
    aiContent.innerHTML = '';
    
    // 显示工具栏
    toolbarWrapper.style.display = 'block';
    toolbarWrapper.classList.add('show');
    
    // 添加编辑模式样式
    aiContent.classList.add('editing');
    if (section) section.classList.add('editing-mode');
    
    try {
      // 创建编辑器
      aiEditor = createEditor({
        selector: '#ai-content',
        html: `<p>${currentText}</p>`,
        config: {
          placeholder: '请输入内容',
          hoverbarKeys: {
            text: { menuKeys: [] },
          },
        },
        mode: 'default',
      });
      
      console.log('AI编辑器创建成功');
      
      // 创建工具栏
      createToolbar({
        editor: aiEditor,
        selector: '#ai-toolbar',
        mode: 'default',
      });
      
      console.log('AI工具栏创建成功');
    } catch (error) {
      console.error('创建AI编辑器失败:', error);
      alert('创建编辑器失败: ' + error.message);
    }
  };

  // 编辑按钮点击事件
  const editOriginalBtn = document.getElementById('edit-original');
  const editAiBtn = document.getElementById('edit-ai');
  
  if (editOriginalBtn) {
    console.log('原文编辑按钮已绑定');
    editOriginalBtn.addEventListener('click', (e) => {
      console.log('点击了原文编辑按钮');
      e.preventDefault();
      e.stopPropagation();
      initOriginalEditor();
    });
  } else {
    console.error('找不到原文编辑按钮');
  }
  
  if (editAiBtn) {
    console.log('AI编辑按钮已绑定');
    editAiBtn.addEventListener('click', (e) => {
      console.log('点击了AI编辑按钮');
      e.preventDefault();
      e.stopPropagation();
      initAiEditor();
    });
  } else {
    console.error('找不到AI编辑按钮');
  }

  const actions = document.querySelectorAll('[data-action]');
  actions.forEach((node) => {
    const action = node.getAttribute('data-action');
    node.style.cursor = 'pointer';
    node.addEventListener('click', () => {
      // 如果有编辑器，保存编辑后的内容
      if (originalEditor || aiEditor) {
        const comparisonData = JSON.parse(localStorage.getItem('ai-writing-comparison') || '{}');
        
        if (originalEditor) {
          comparisonData.originalText = originalEditor.getHtml();
        }
        if (aiEditor) {
          comparisonData.aiGeneratedText = aiEditor.getHtml();
        }
        
        localStorage.setItem('ai-writing-comparison', JSON.stringify(comparisonData));
      }
      
      // 记录用户选择
      if (action) {
        localStorage.setItem('ai-writing-choice', action);
      }
      // 返回主写作页面
      go('../writing-workspace/writing-workspace.html');
    });
  });
});
