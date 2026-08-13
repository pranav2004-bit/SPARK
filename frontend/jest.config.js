/** @type {import('jest').Config} */
module.exports = {
  // Default environment for pure-logic / Node tests (middleware, hooks, api).
  // Component tests that need a DOM use the @jest-environment jsdom docblock
  // at the top of their file — Jest respects per-file environment overrides.
  testEnvironment: "node",
  transform: {
    "^.+\\.tsx?$": [
      "ts-jest",
      {
        tsconfig: {
          module: "commonjs",
          esModuleInterop: true,
          jsx: "react-jsx",
          strict: false,
        },
      },
    ],
  },
  moduleNameMapper: {
    // Path alias resolution
    "^@/(.*)$": "<rootDir>/src/$1",
    // Static asset stubs — Next.js Image and SVG imports are irrelevant in tests.
    "\\.(svg|png|jpg|jpeg|gif|webp)$": "<rootDir>/src/tests/__mocks__/fileMock.js",
    // CSS module stub — not used in this project but guards against future imports.
    "\\.module\\.css$": "<rootDir>/src/tests/__mocks__/styleMock.js",
  },
  // jest-dom matchers (toBeInTheDocument, toHaveValue, etc.) loaded globally
  // for all test files — component tests use these without a per-file import.
  setupFilesAfterEnv: ["<rootDir>/src/tests/setupTests.ts"],
  testMatch: ["**/tests/**/*.test.ts", "**/tests/**/*.test.tsx"],
  clearMocks: true,
  // Exclude .next build output — prevents haste-map "name collision" warning
  // that occurs because .next/standalone/package.json shares the same "name"
  // field as the root package.json.
  modulePathIgnorePatterns: ["<rootDir>/.next/"],
  testPathIgnorePatterns: ["<rootDir>/.next/", "<rootDir>/node_modules/"],
};
