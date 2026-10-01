from playwright.async_api import Page


async def read_page(page: Page, max_text_length: int) -> dict[str, object]:
    data = await page.evaluate(
        """() => {
          const visible = (element) => {
            const style = getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              Number(style.opacity) !== 0 && element.getClientRects().length > 0;
          };
          const text = (element) => (element.innerText || element.textContent || '')
            .replace(/\\s+/g, ' ').trim();
          const elements = (selector) => Array.from(document.querySelectorAll(selector)).filter(visible);
          const attribute = (element, name) => element.getAttribute(name) || '';
          return {
            title: document.title || '',
            url: location.href,
            visible_text: document.body?.innerText || '',
            headings: elements('h1,h2,h3,h4,h5,h6').map(text).filter(Boolean),
            buttons: elements('button, input[type="button"], input[type="submit"]').map((element) => ({
              text: text(element) || attribute(element, 'value'),
              aria_label: attribute(element, 'aria-label'),
              disabled: Boolean(element.disabled),
            })),
            inputs: elements('input:not([type="checkbox"]):not([type="radio"]), textarea').map((element) => ({
              type: element.type || 'textarea', name: attribute(element, 'name'), id: element.id || '',
              placeholder: attribute(element, 'placeholder'), required: Boolean(element.required),
              aria_label: attribute(element, 'aria-label'),
            })),
            links: elements('a[href]').map((element) => ({ text: text(element), href: element.href })),
            forms: elements('form').map((element) => ({
              name: attribute(element, 'name'), action: element.action, method: (element.method || 'get').toUpperCase(),
            })),
            checkboxes: elements('input[type="checkbox"]').map((element) => ({
              name: attribute(element, 'name'), id: element.id || '', checked: Boolean(element.checked),
              required: Boolean(element.required),
            })),
            radio_buttons: elements('input[type="radio"]').map((element) => ({
              name: attribute(element, 'name'), value: attribute(element, 'value'), checked: Boolean(element.checked),
            })),
            selects: elements('select').map((element) => ({
              name: attribute(element, 'name'), id: element.id || '',
              options: Array.from(element.options).map((option) => ({ text: text(option), value: option.value })),
            })),
          };
        }"""
    )
    visible_text = "\n".join(line.strip() for line in str(data["visible_text"]).splitlines() if line.strip())
    data["visible_text"] = visible_text[:max_text_length]
    data["url"] = page.url
    return data