import fs from "node:fs/promises";
import * as dotenv from "dotenv";

dotenv.config();

const sleep = (msec: number) =>
  new Promise((resolve) => setTimeout(resolve, msec));

const followRedirect = async (
  url: string,
  cookies: string | null
): Promise<[string, string | null]> => {
  console.log("followRedirect url:", url);
  const res = await fetch(url, {
    method: "HEAD",
    redirect: "manual",
    headers: { Cookie: cookies ? cookies : "" },
  });
  console.log("followRedirect status:", res.status, res.statusText);
  const newCookies = res.headers.get("Set-Cookie") || cookies;
  console.log("followRedirect cookies:", newCookies?.length);
  if (res.status >= 300 && res.status < 400) {
    const location = res.headers.get("location");
    if (location) {
      if (location.startsWith("http")) {
        return await followRedirect(location, newCookies);
      } else {
        const origin = new URL(url).origin;
        return await followRedirect(origin + location, newCookies);
      }
    }
  }
  return [url, newCookies];
};

const followRefresh = async (
  url: string,
  cookies: string | null
): Promise<[string, string | null]> => {
  console.log("followRefresh url:", url);
  const res = await fetch(url, {
    headers: { Cookie: cookies ? cookies : "" },
  });
  console.log("followRefresh status:", res.status, res.statusText);
  const resText = await res.text();
  const newCookies = res.headers.get("Set-Cookies") || cookies;
  console.log("followRefresh cookies:", newCookies?.length);
  const metaRefreshList = resText
    .split("\n")
    .filter(
      (line) =>
        line.toLowerCase().startsWith("<meta") &&
        line.toLowerCase().includes("refresh")
    );
  if (metaRefreshList.length === 0) {
    return [url, newCookies];
  }
  const refreshPath = metaRefreshList[0]
    .replaceAll('"', "")
    .split("=")[3]
    .replace(">", "");
  console.log("followRefresh", refreshPath);
  if (refreshPath.startsWith("http")) {
    return await followRefresh(refreshPath, newCookies);
  } else {
    const origin = new URL(url).origin;
    return await followRefresh(origin + refreshPath, newCookies);
  }
};

// list of all documents
const docsUrlsFile = await fs.readFile(
  "data/www.undocs.org/all_docs_urls_uniq.txt",
  "utf-8"
);
const urls = docsUrlsFile.split("\n");
console.info("urls:", urls.length);

// fetch and save all documents
for (const url of urls.reverse()) {
  console.log("----- ----- -----");
  console.info("fetch:", url);
  console.info(urls.indexOf(url), "/", urls.length);
  if (0 === url.length) {
    continue;
  }
  if (url.includes("&AREA=UNDOC") || url.includes("&Area=UNDOC")) {
    continue;
  }
  try {
    const resolutionId = url
      .replace("http://", "")
      .replace("https://", "")
      .replace("www.undocs.org/", "")
      .replace("undocs.org/", "")
      .replace("en/", "")
      .replaceAll(" ", "")
      .replaceAll("%20", "")
      .toUpperCase();
    console.log("resolutionId:", resolutionId);
    if (
      !resolutionId.includes("2020") &&
      !resolutionId.includes("2021") &&
      !resolutionId.includes("2022") &&
      !resolutionId.includes("2023")
    ) {
      continue;
    }
    try {
      const alreadyFetched = (
        await fs.lstat(
          `./en/pdfs/${resolutionId.replaceAll(" ", "")}/resolution.pdf`
        )
      ).isFile();
      if (alreadyFetched) {
        continue;
      }
    } catch (error) {
      console.log("");
    }

    const englishUrl = "https://www.undocs.org/en/" + resolutionId;
    console.log("englishUrl:", englishUrl);

    const myCookies = process.env["UNDOCS_COOKIES"] || "";

    const [redirectedUrl, redirectCookies] = await followRedirect(
      englishUrl,
      myCookies
    );
    const [refreshedUrl, cookies] = await followRefresh(
      redirectedUrl,
      redirectCookies
    );

    console.log();
    console.log(refreshedUrl);
    console.log();

    const userAgent = process.env["UNDOCS_UA"] || "";
    const referrer = new URL(refreshedUrl).origin;

    const res = await fetch(refreshedUrl, {
      referrer: referrer,
      headers: { Cookie: cookies ? cookies : "", "User-Agent": userAgent },
    });

    const contentType = res.headers.get("Content-Type");
    console.log(contentType);
    if (contentType !== "application/pdf") {
      throw Error("Response is not PDF");
    }

    const content = await res.blob();
    const buffer = Buffer.from(await content.arrayBuffer());

    console.log("res length:", buffer.length);

    await fs.mkdir(`./en/pdfs/${resolutionId.replaceAll(" ", "")}/`, {
      recursive: true,
    });
    await fs.writeFile(
      `./en/pdfs/${resolutionId.replaceAll(" ", "")}/resolution.pdf`,
      buffer
    );
  } catch (error) {
    console.error(error);
  }
  await sleep(3000);
  console.log("----- ----- -----");
}
