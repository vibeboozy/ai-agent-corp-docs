export class AnalyticsTab {
  constructor(container) {
    this.container = container;
  }

  mount() {
    this.container.innerHTML = `
      <div style="padding: 40px 24px; max-width: 900px; margin: 0 auto; width: 100%; display: flex; flex-direction: column; gap: 24px;">
        <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--color-border); padding-bottom: 16px;">
          <div>
            <h2 style="font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); color: var(--color-text-main);">
              Аналитика пробелов в регламентах
            </h2>
            <p style="font-size: var(--font-size-sm); color: var(--color-text-muted); margin-top: 4px;">
              Автоматическое выявление серых зон и недостающих инструкций на основе нерешённых вопросов
            </p>
          </div>
          <span class="badge badge-clarify">Модуль в разработке</span>
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px;">
          <div style="background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 20px;">
            <div style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-weight: 600; text-transform: uppercase;">
              Частота эскалаций
            </div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--color-primary); margin: 8px 0;">14.2%</div>
            <div style="font-size: var(--font-size-xs); color: var(--color-status-answer);">↓ -3.8% после доиндексации БЗ</div>
          </div>

          <div style="background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 20px;">
            <div style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-weight: 600; text-transform: uppercase;">
              Полнота регламентов
            </div>
            <div style="font-size: 2rem; font-weight: 700; color: var(--color-status-answer); margin: 8px 0;">88.5%</div>
            <div style="font-size: var(--font-size-xs); color: var(--color-text-muted);">Ключевых сценариев закрыто</div>
          </div>

          <div style="background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 20px;">
            <div style="font-size: var(--font-size-xs); color: var(--color-text-muted); font-weight: 600; text-transform: uppercase;">
              Топ пробелов
            </div>
            <div style="font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-main); margin-top: 10px;">
              1. Реорганизация юрлиц (4)<br>
              2. Нестандартные скидки (2)<br>
              3. Смена владельца ключа (1)
            </div>
          </div>
        </div>

        <div style="background: var(--color-surface-subtle); border: 1px dashed var(--color-border); border-radius: var(--radius-xl); padding: 32px; text-align: center; color: var(--color-text-muted);">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom: 12px; color: var(--color-primary);">
            <path d="M3 3v18h18"/>
            <path d="m19 9-5 5-4-4-3 3"/>
          </svg>
          <p style="font-weight: 500; color: var(--color-text-main);">Модуль кластеризации запросов будет доступен в следующем релизе</p>
          <p style="font-size: var(--font-size-sm); margin-top: 4px;">Позволит руководителям Отдела качества автоматически генерировать проекты новых пунктов регламентов на основе частых обращений.</p>
        </div>
      </div>
    `;
  }

  unmount() {
    this.container.innerHTML = '';
  }
}
