import { expect, test, type Page } from "@playwright/test";

async function sidebarMetrics(page: Page) {
  return page.locator('.workspace-sidebar').evaluate(sidebar => {
    const style = getComputedStyle(sidebar);
    const nav = getComputedStyle(sidebar.querySelector('nav a:not(.active)')!);
    const active = getComputedStyle(sidebar.querySelector('nav a.active')!);
    const footerElement = sidebar.querySelector('.workspace-sidebar-bottom')!;
    const footer = footerElement.getBoundingClientRect();
    const footerStyle = getComputedStyle(footerElement);
    return { width: sidebar.getBoundingClientRect().width, background: style.backgroundColor,
      font: nav.fontSize, weight: nav.fontWeight, padding: nav.padding, navHeight: nav.minHeight,
      activeColor: active.color, activeBorder: active.borderColor, footerHeight: footer.height, footerY: footer.y,
      footerBackground: footerStyle.backgroundColor, footerBorder: footerStyle.border,
      footerRadius: footerStyle.borderRadius, footerPadding: footerStyle.padding, footerGap: footerStyle.gap };
  });
}

for (const width of [320, 390, 768, 1440, 1920]) for (const locale of ['zh', 'en']) for (const theme of ['light', 'dark']) {
  test(`shared sidebar and compact task configuration ${width} ${locale} ${theme}`, async ({ page }, info) => {
    let role = 'user';
    const requests: string[] = [];
    const zh = locale === 'zh';
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(({ locale, theme }) => {
      localStorage.setItem('dashanbing-locale', locale);
      localStorage.setItem('dashanbing-theme', theme);
    }, { locale, theme });
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname;
      requests.push(path);
      const body = path === '/api/v1/users/me' ? { id: 7, username: width === 320 ? 'reviewer_with_a_very_long_account_name' : 'reviewer', email: 'reviewer@example.test', role, is_active: true }
        : path === '/api/v1/presets' ? [] : { items: [], total: 0, page: 1, page_size: 20 };
      await route.fulfill({ json: body });
    });
    await page.goto('/workspace/new');
    const config = page.getByRole('button', { name: zh ? '配置' : 'Configure', exact: true });
    const title = page.getByLabel(zh ? '任务标题' : 'Task title', { exact: true });
    await expect(config).toBeVisible();
    const a = (await title.boundingBox())!, b = (await config.boundingBox())!;
    expect(Math.abs(a.y - b.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(a.height - b.height)).toBeLessThanOrEqual(1);
    await expect(page.getByRole('combobox')).toHaveCount(0);
    await config.click();
    const panel = page.getByRole('dialog', { name: zh ? '配置' : 'Configure', exact: true });
    await expect(panel).toBeVisible();
    const method = panel.getByRole('combobox', { name: zh ? '注册方式' : 'Registration method', exact: true });
    const count = panel.getByRole('combobox', { name: zh ? '注册人数' : 'Number of people', exact: true });
    expect(Math.abs((await method.boundingBox())!.width - (await count.boundingBox())!.width)).toBeLessThanOrEqual(1);
    const bounds = (await panel.boundingBox())!;
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    await method.selectOption('lineup'); await count.selectOption('4');
    expect(await method.evaluate(select => {
      const style = getComputedStyle(select);
      const canvas = document.createElement('canvas');
      const context = canvas.getContext('2d')!;
      context.font = `${style.fontSize} ${style.fontFamily}`;
      return context.measureText((select as HTMLSelectElement).selectedOptions[0].text).width + parseFloat(style.paddingLeft) + parseFloat(style.paddingRight) <= select.clientWidth;
    })).toBe(true);
    await panel.getByRole('radio', { name: zh ? /完整/ : /Full/ }).check();
    if (width === 390 || width === 1440) await page.screenshot({ path: info.outputPath('task-configuration.png') });
    await page.keyboard.press('Escape'); await expect(config).toBeFocused();
    await config.click(); await expect(count).toHaveValue('4');
    await title.click(); await expect(panel).toHaveCount(0);
    await page.setViewportSize({ width, height: 480 });
    await config.click();
    const shortBounds = (await panel.boundingBox())!;
    expect(shortBounds.y).toBeGreaterThanOrEqual(0);
    expect(shortBounds.y + shortBounds.height).toBeLessThanOrEqual(480);
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width, height: 900 });

    async function expand(admin: boolean) {
      if (width < 768) await page.getByRole('button', { name: zh ? (admin ? '打开管理菜单' : '打开工作台菜单') : (admin ? 'Open administrator menu' : 'Open workspace menu'), exact: true }).click();
      else if (width < 1280) {
        await page.getByRole('button', { name: zh ? '展开侧边栏' : 'Expand sidebar', exact: true }).click();
        await expect(page.locator('.workspace-shell')).not.toHaveClass(/is-collapsed/);
      }
      await expect(page.locator('.workspace-sidebar')).toBeVisible();
    }
    await expand(false);
    const ordinary = await sidebarMetrics(page);
    if (width === 390 || width === 1440) await page.locator('.workspace-sidebar-bottom').screenshot({ path: info.outputPath('user-account-row.png') });
    role = 'admin'; requests.length = 0;
    await page.goto('/admin/users'); await expand(true);
    expect(await sidebarMetrics(page)).toEqual(ordinary);
    await expect(page.locator('.workspace-recent')).toHaveCount(0);
    await expect(page.locator('.workspace-nav a')).toHaveCount(6);
    expect(requests).not.toContain('/api/v1/tasks');
    const footer = page.locator('.workspace-sidebar-bottom');
    await expect(footer.getByRole('button')).toHaveCount(4);
    await expect(footer.getByRole('button', { name: zh ? '退出登录' : 'Log out', exact: true })).toBeVisible();
    const row = await footer.evaluate(el => {
      const bounds = el.getBoundingClientRect();
      const centers = [...el.querySelectorAll('button, .workspace-account-name')].map(node => {
        const rect = node.getBoundingClientRect();
        return rect.y + rect.height / 2;
      });
      return { aligned: Math.max(...centers) - Math.min(...centers) <= 1, fits: el.scrollWidth <= el.clientWidth, height: bounds.height };
    });
    expect(row).toEqual({ aligned: true, fits: true, height: ordinary.footerHeight });
    if (width === 390 || width === 1440) await footer.screenshot({ path: info.outputPath('admin-account-row.png') });
    if (width === 390 || width === 1440) await page.screenshot({ path: info.outputPath('admin-sidebar.png') });
    const account = page.getByRole('button', { name: /(?:账户|Account).*reviewer/ });
    await account.click();
    await expect(page.getByRole('button', { name: zh ? '退出登录' : 'Log out', exact: true })).toBeVisible();
    await page.keyboard.press('Escape'); await expect(account).toBeFocused();
    if (width >= 768) {
      await page.getByRole('button', { name: zh ? '收起侧边栏' : 'Collapse sidebar', exact: true }).click();
      const expandButton = page.getByRole('button', { name: zh ? '展开侧边栏' : 'Expand sidebar', exact: true });
      await page.mouse.move(width - 1, 450);
      await expect(page.locator('.workspace-sidebar')).toBeHidden();
      await expandButton.hover(); await expect(page.locator('.workspace-sidebar')).toBeVisible();
      expect(await page.locator('.workspace-main').evaluate(el => getComputedStyle(el).marginLeft)).toBe('0px');
      await page.keyboard.press('Escape'); await expect(expandButton).toBeFocused();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
