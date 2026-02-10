document.addEventListener('DOMContentLoaded', () => {
  const go = (path) => {
    window.location.href = path;
  };

  let originalEditor = null;
  let aiEditor = null;

  const comparisonDataStr = localStorage.getItem('ai-writing-comparison');
  if (comparisonDataStr) {
    try {
      const comparisonData = JSON.parse(comparisonDataStr);
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

  const initEditor = async (kind) => {
    if (!window.TiptapEditorFactory) {
      alert('Tiptap 编辑器未加载，请刷新页面重试');
      return;
    }

    const isOriginal = kind === 'original';
    const contentId = isOriginal ? 'original-content' : 'ai-content';
    const toolbarId = isOriginal ? 'original-toolbar' : 'ai-toolbar';
    const wrapperId = isOriginal ? 'original-toolbar-wrapper' : 'ai-toolbar-wrapper';
    const cardSelector = isOriginal ? '.original-card' : '.ai-card';

    if (isOriginal && originalEditor) return;
    if (!isOriginal && aiEditor) return;

    const contentEl = document.getElementById(contentId);
    const toolbarWrapper = document.getElementById(wrapperId);
    const card = contentEl ? contentEl.closest(cardSelector) : null;
    if (!contentEl || !toolbarWrapper) return;

    const currentHtml = contentEl.innerHTML || '<p></p>';
    contentEl.innerHTML = '';
    toolbarWrapper.style.display = 'block';
    toolbarWrapper.classList.add('show');
    contentEl.classList.add('editing');
    if (card) card.classList.add('editing-mode');

    try {
      const editor = await window.TiptapEditorFactory.createEditor({
        selector: `#${contentId}`,
        toolbarSelector: `#${toolbarId}`,
      });
      editor.setHtml(currentHtml);
      if (isOriginal) originalEditor = editor;
      else aiEditor = editor;
    } catch (error) {
      console.error('创建 Tiptap 编辑器失败:', error);
      alert('创建编辑器失败: ' + error.message);
    }
  };

  const editOriginalBtn = document.getElementById('edit-original');
  const editAiBtn = document.getElementById('edit-ai');
  if (editOriginalBtn) editOriginalBtn.addEventListener('click', async (e) => { e.preventDefault(); e.stopPropagation(); await initEditor('original'); });
  if (editAiBtn) editAiBtn.addEventListener('click', async (e) => { e.preventDefault(); e.stopPropagation(); await initEditor('ai'); });

  const actions = document.querySelectorAll('[data-action]');
  actions.forEach((node) => {
    const action = node.getAttribute('data-action');
    node.style.cursor = 'pointer';
    node.addEventListener('click', () => {
      if (originalEditor || aiEditor) {
        const comparisonData = JSON.parse(localStorage.getItem('ai-writing-comparison') || '{}');
        if (originalEditor) comparisonData.originalText = originalEditor.getHtml();
        if (aiEditor) comparisonData.aiGeneratedText = aiEditor.getHtml();
        localStorage.setItem('ai-writing-comparison', JSON.stringify(comparisonData));
      }
      if (action === 'back') go('/project_document/writing-workspace/1');
      if (action === 'save') alert('已保存');
    });
  });
});
