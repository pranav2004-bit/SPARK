/**
 * Global Jest setup — runs after the test framework is installed in each
 * test file's environment.
 *
 * @testing-library/jest-dom extends Jest's expect() with DOM matchers:
 *   toBeInTheDocument(), toHaveValue(), toBeDisabled(), toHaveTextContent() …
 *
 * This file is referenced in jest.config.js → setupFilesAfterEnv so every
 * test file (both node-env and jsdom-env) automatically has these matchers
 * without needing a per-file import.
 */
import "@testing-library/jest-dom";
