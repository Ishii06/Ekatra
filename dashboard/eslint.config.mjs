import nextVitals from "eslint-config-next/core-web-vitals";

const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "lib/data/experiments/**",
    ],
  },
  ...nextVitals,
];

export default config;
