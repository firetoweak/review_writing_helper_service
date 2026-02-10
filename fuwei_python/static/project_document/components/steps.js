// static/project_document/components/steps.js
(function (window) {
  const titles = ['填写构想', '确认大纲', '智能写作', '预览检查','全文评审'];

  function renderSimple(activeStep) {
    return `
      <div class="steps-bar">
        ${titles.map((title, idx) => {
          const step = idx + 1;
          const active = step === activeStep;
          return `
            <div class="flex-row items-center" data-step="${step}">
              <div class="flex-col justify-start items-center shrink-0 step-badge ${active ? '' : 'step-badge--inactive'}">
                <span class="step-number">${step}</span>
              </div>
              <span class="step-label ${active ? '' : 'step-label--inactive'}">${title}</span>
              ${step === titles.length ? '' : '<div class="shrink-0 step-divider"></div>'}
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function renderWorkspace(activeStep) {
    return `
      <div class="flex-row items-center steps-workspace" aria-label="写作流程步骤">
        ${titles.map((title, idx) => {
          const step = idx + 1;
          const active = step === activeStep;
          const circleClass = active ? 'step-number-circle-active' : 'step-number-circle';
          const labelClass = active ? 'step-label-text step-label-active' : 'step-label-text step-label-inactive';
          return `
            <div class="flex-row items-center" data-step="${step}">
              <div class="flex-col justify-start items-center shrink-0 ${circleClass}">
                <span class="step-number-text">${step}</span>
              </div>
              <span class="${labelClass} ml-space-nine">${title}</span>
              ${step === titles.length ? '' : '<div class="shrink-0 step-divider ml-space-nine"></div>'}
            </div>
          `;
        }).join('')}
      </div>
    `;
  }

  function mount(container, options) {
    if (!container) return;
    const {
      active = 1,
      routes = {},
      onCurrent = () => {},
      variant = 'simple',
    } = options || {};

    const html = variant === 'workspace' ? renderWorkspace(active) : renderSimple(active);
    container.innerHTML = html;

    const stepItems = container.querySelectorAll('[data-step]');
    stepItems.forEach((item) => {
      const step = Number(item.getAttribute('data-step'));
      const target = routes[step];
      item.style.cursor = 'pointer';
      item.addEventListener('click', () => {
        if (target) {
          window.location.href = target;
        } else {
          onCurrent(step);
        }
      });
    });
  }
  window.StepsComponent = { mount };
})(window);
