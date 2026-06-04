import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  ...nextVitals,
  ...nextTypescript,
  {
    ignores: [".next/**", "out/**", "storybook-static/**", "coverage/**", "next-env.d.ts"],
  },
];

export default eslintConfig;
