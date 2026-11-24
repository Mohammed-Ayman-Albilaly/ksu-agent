import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach } from "vitest";

// React 19 only suppresses its "not wrapped in act" warning when the test environment
// says it is one.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

// jsdom implements neither, and the message list scrolls itself into view.
Element.prototype.scrollTo = () => {};
Element.prototype.scrollIntoView = () => {};

// Node defines an experimental global localStorage that is undefined unless the process
// was started with --localstorage-file, and it shadows jsdom's on the window the tests see.
// A small in-memory store stands in, so the storage tests exercise the code they mean to.
function memoryStorage(): Storage {
  const store = new Map<string, string>();

  return {
    get length() {
      return store.size;
    },
    key: (index: number) => [...store.keys()][index] ?? null,
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => {
      store.clear();
    },
  };
}

for (const name of ["localStorage", "sessionStorage"] as const) {
  if (!window[name]) {
    Object.defineProperty(window, name, {
      configurable: true,
      value: memoryStorage(),
    });
  }
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
});
