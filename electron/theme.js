// Apply the saved theme before the stylesheet loads to avoid a light flash.
(() => {
  let theme = 'light';
  try {
    if (localStorage.getItem('clipa-theme') === 'dark') theme = 'dark';
  } catch {
    // Keep the default theme when local storage is unavailable.
  }
  document.documentElement.dataset.theme = theme;
})();
