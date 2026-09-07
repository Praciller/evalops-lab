const config = (ctx) => {
  const filePath = ctx?.file ? (typeof ctx.file === "string" ? ctx.file : ctx.file.path ?? "") : "";
  if (filePath.includes("node_modules") || filePath.endsWith(".module.css")) {
    return { plugins: {} };
  }
  return {
    plugins: {
      "@tailwindcss/postcss": {},
    },
  };
};

export default config;
