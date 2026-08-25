export function formatISTDateTime(isoString?: string | null): string {
  if (!isoString) return "N/A";
  try {
    let str = isoString.trim();
    // Ensure ISO string is explicitly marked as UTC (with 'Z') if missing timezone offset
    if (!str.endsWith("Z") && !str.includes("+") && !/-\d{2}:\d{2}$/.test(str)) {
      str += "Z";
    }

    const date = new Date(str);
    if (isNaN(date.getTime())) return isoString;

    return new Intl.DateTimeFormat("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true
    }).format(date) + " IST";
  } catch (err) {
    return isoString;
  }
}
