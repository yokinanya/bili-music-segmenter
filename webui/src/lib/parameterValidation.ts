export interface MaterialInput extends HTMLElement {
  value: string;
  disabled: boolean;
  validationMessage: string;
  checkValidity: () => boolean;
  reportValidity: () => boolean;
}

function inActivePane(field: MaterialInput, root: HTMLElement): boolean {
  let ancestor = field.parentElement;
  while (ancestor && ancestor !== root) {
    if (ancestor.hidden && !ancestor.classList.contains('disclosure-content')) return false;
    ancestor = ancestor.parentElement;
  }
  return true;
}

export function validateParameters(root: HTMLElement): boolean {
  const fields = Array.from(root.querySelectorAll<MaterialInput>('md-outlined-text-field'));
  const invalid = fields.filter((field) => !field.disabled && inActivePane(field, root) && !field.checkValidity());
  if (!invalid.length) return true;
  const first = invalid[0];
  let ancestor = first.parentElement;
  while (ancestor && ancestor !== root) {
    if (ancestor.hidden) {
      const trigger = ancestor.previousElementSibling;
      if (trigger instanceof HTMLButtonElement) trigger.click();
    }
    ancestor = ancestor.parentElement;
  }
  requestAnimationFrame(() => {
    invalid.forEach((field) => field.reportValidity());
    first.focus();
  });
  return false;
}
