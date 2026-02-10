// static/project_document/tiptap-editor.js
// Tiptap 编辑器工厂：支持 Markdown <-> 富文本闭环，含 GFM 表格、代码高亮和自定义 section 容器语法。
(function () {
  const CDN = {
    core: 'https://cdn.jsdelivr.net/npm/@tiptap/core@2.10.4/+esm',
    starterKit: 'https://cdn.jsdelivr.net/npm/@tiptap/starter-kit@2.10.4/+esm',
    table: 'https://cdn.jsdelivr.net/npm/@tiptap/extension-table@2.10.4/+esm',
    tableRow: 'https://cdn.jsdelivr.net/npm/@tiptap/extension-table-row@2.10.4/+esm',
    tableCell: 'https://cdn.jsdelivr.net/npm/@tiptap/extension-table-cell@2.10.4/+esm',
    tableHeader: 'https://cdn.jsdelivr.net/npm/@tiptap/extension-table-header@2.10.4/+esm',
    codeBlockLowlight: 'https://cdn.jsdelivr.net/npm/@tiptap/extension-code-block-lowlight@2.10.4/+esm',
    markdown: 'https://cdn.jsdelivr.net/npm/@tiptap/markdown@2.10.4/+esm',
    lowlight: 'https://cdn.jsdelivr.net/npm/lowlight@2.9.0/+esm',
    langJs: 'https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/languages/javascript.js/+esm',
    langPy: 'https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/languages/python.js/+esm',
    langJson: 'https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/es/languages/json.js/+esm',
    mdContainer: 'https://cdn.jsdelivr.net/npm/markdown-it-container@3.0.0/+esm'
  };

  function parseSectionAttrs(raw) {
    const attrs = { color: '#fff', title: null };
    if (!raw) return attrs;

    const colorMatch = raw.match(/color\s*=\s*([^\s}]+)/);
    if (colorMatch && colorMatch[1]) attrs.color = colorMatch[1].replace(/["']/g, '');

    const titleMatch = raw.match(/title\s*=\s*"([^"]*)"/);
    if (titleMatch && titleMatch[1] !== undefined) attrs.title = titleMatch[1];

    return attrs;
  }

  function attrsToSectionParam(attrs) {
    const color = (attrs && attrs.color) || '#fff';
    const title = attrs && attrs.title ? ` title="${String(attrs.title).replace(/"/g, '\\"')}"` : '';
    return `color=${color}${title}`;
  }

  async function ensureModules() {
    if (window.__TIPTAP_WRITING_MODULES__) return window.__TIPTAP_WRITING_MODULES__;

    const [core, starterKit, table, tableRow, tableCell, tableHeader, codeBlockLowlight, markdown, lowlight, langJs, langPy, langJson, mdContainer] = await Promise.all([
      import(CDN.core),
      import(CDN.starterKit),
      import(CDN.table),
      import(CDN.tableRow),
      import(CDN.tableCell),
      import(CDN.tableHeader),
      import(CDN.codeBlockLowlight),
      import(CDN.markdown),
      import(CDN.lowlight),
      import(CDN.langJs),
      import(CDN.langPy),
      import(CDN.langJson),
      import(CDN.mdContainer)
    ]);

    // lowlight 语言注册示例：js/python/json
    const ll = lowlight.lowlight || lowlight.default || lowlight;
    ll.registerLanguage('javascript', langJs.default || langJs);
    ll.registerLanguage('python', langPy.default || langPy);
    ll.registerLanguage('json', langJson.default || langJson);

    window.__TIPTAP_WRITING_MODULES__ = {
      Editor: core.Editor,
      Node: core.Node,
      mergeAttributes: core.mergeAttributes,
      StarterKit: starterKit.default,
      Table: table.default,
      TableRow: tableRow.default,
      TableCell: tableCell.default,
      TableHeader: tableHeader.default,
      CodeBlockLowlight: codeBlockLowlight.default,
      Markdown: markdown.Markdown || markdown.default,
      lowlight: ll,
      markdownItContainer: mdContainer.default || mdContainer
    };

    return window.__TIPTAP_WRITING_MODULES__;
  }

  function createToolbar(toolbarSelector, editor, simpleMode) {
    const toolbar = typeof toolbarSelector === 'string' ? document.querySelector(toolbarSelector) : toolbarSelector;
    if (!toolbar) return;

    toolbar.innerHTML = '';
    const buttons = [
      { text: 'B', action: () => editor.chain().focus().toggleBold().run() },
      { text: 'I', action: () => editor.chain().focus().toggleItalic().run() },
      { text: 'H2', action: () => editor.chain().focus().toggleHeading({ level: 2 }).run() },
      { text: '• 列表', action: () => editor.chain().focus().toggleBulletList().run() },
      { text: '</>', action: () => editor.chain().focus().toggleCodeBlock().run() }
    ];

    if (!simpleMode) {
      buttons.push({ text: '插入表格', action: () => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run() });
    }

    buttons.forEach((cfg) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tiptap-toolbar-btn';
      btn.textContent = cfg.text;
      btn.addEventListener('click', cfg.action);
      toolbar.appendChild(btn);
    });
  }

  async function createEditor(config) {
    const modules = await ensureModules();
    const {
      Editor,
      Node,
      mergeAttributes,
      StarterKit,
      Table,
      TableRow,
      TableCell,
      TableHeader,
      CodeBlockLowlight,
      Markdown,
      lowlight,
      markdownItContainer
    } = modules;

    const element = typeof config.selector === 'string' ? document.querySelector(config.selector) : config.selector;
    if (!element) throw new Error('编辑器容器不存在');

    const SectionContainer = Node.create({
      name: 'sectionContainer',
      group: 'block',
      content: 'block+',
      attrs: {
        color: { default: '#fff' },
        title: { default: null }
      },
      parseHTML() {
        return [{ tag: 'div.custom-section' }];
      },
      renderHTML({ HTMLAttributes }) {
        const color = HTMLAttributes.color || '#fff';
        const title = HTMLAttributes.title || null;

        return ['div', mergeAttributes({
          class: 'custom-section',
          style: `background: ${color};`,
          'data-section-color': color,
          title
        }, HTMLAttributes), 0];
      },
      // Markdown 导出（@tiptap/markdown 会调用该渲染配置）
      renderMarkdown({ node, content }) {
        const attrs = attrsToSectionParam(node.attrs || {});
        return `:::section{${attrs}}\n${content}\n:::`;
      }
    });

    const markdownExtension = Markdown.configure({
      html: true,
      breaks: true,
      // 关键点：启用 markdown-it GFM 表格 + 自定义 section 容器语法解析
      markdownItSetup(md) {
        md.enable('table');

        md.use(markdownItContainer, 'section', {
          validate(params) {
            return /^section(?:\{.*\})?$/.test((params || '').trim());
          },
          render(tokens, idx) {
            const token = tokens[idx];
            if (token.nesting === 1) {
              const raw = token.info.replace(/^section\s*/, '').trim();
              const attrs = parseSectionAttrs(raw.replace(/^\{|\}$/g, ''));
              const titleAttr = attrs.title ? ` title="${attrs.title.replace(/"/g, '&quot;')}"` : '';
              return `<div class="custom-section" data-section-color="${attrs.color}" data-section-title="${attrs.title || ''}" style="background: ${attrs.color};"${titleAttr}>`;
            }
            return '</div>';
          }
        });
      }
    });

    const simpleMode = !!config.simpleMode;
    const editor = new Editor({
      element,
      extensions: [
        StarterKit,
        Table.configure({ resizable: false }),
        TableRow,
        TableCell,
        TableHeader,
        CodeBlockLowlight.configure({ lowlight }),
        SectionContainer,
        markdownExtension
      ],
      content: '',
      onUpdate() {
        if (typeof config.onChange === 'function') config.onChange();
      }
    });

    if (config.toolbarSelector) {
      createToolbar(config.toolbarSelector, editor, simpleMode);
    }

    const originalGetMarkdown = editor.storage.markdown && editor.storage.markdown.getMarkdown
      ? editor.storage.markdown.getMarkdown.bind(editor.storage.markdown)
      : () => '';

    // 统一导出 hook：保留 :::section{...} 自定义语法
    if (editor.storage.markdown) {
      editor.storage.markdown.getMarkdown = () => {
        const md = originalGetMarkdown();
        return md
          .replace(/<div class="custom-section"[^>]*data-section-color="([^"]+)"[^>]*data-section-title="([^"]*)"[^>]*>[\s\S]*?<\/div>/g, (m, color, title) => {
            return `:::section{${attrsToSectionParam({ color, title: title || null })}}\n\n:::`;
          });
      };
    }

    if (config.markdown) {
      editor.commands.setContent(config.markdown, 'markdown');
    }

    return {
      instance: editor,
      storage: editor.storage,
      getHtml: () => editor.getHTML(),
      getText: () => editor.getText(),
      getMarkdown: () => editor.storage.markdown.getMarkdown(),
      setHtml: (html) => editor.commands.setContent(html || ''),
      setText: (text) => editor.commands.setContent(`<p>${(text || '').replace(/</g, '&lt;')}</p>`),
      setMarkdown: (markdownText) => editor.commands.setContent(markdownText || '', 'markdown'),
      onChange: (cb) => editor.on('update', cb),
      destroy: () => editor.destroy()
    };
  }

  window.TiptapEditorFactory = {
    createEditor
  };
})();
