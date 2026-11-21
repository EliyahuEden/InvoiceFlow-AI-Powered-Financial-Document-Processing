import "@testing-library/jest-dom/vitest";

// jsdom lacks these browser APIs; cmdk (command palette) uses them.
class ResizeObserverShim { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= ResizeObserverShim;
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = function scrollIntoView() {};
