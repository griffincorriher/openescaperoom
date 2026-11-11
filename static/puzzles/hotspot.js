export function isHotspotHit(regions, tolerance, x, y) {
  if (
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    x < 0 ||
    x > 100 ||
    y < 0 ||
    y > 100 ||
    !Number.isFinite(tolerance) ||
    tolerance < 0 ||
    tolerance > 10 ||
    !Array.isArray(regions)
  ) {
    return { hit: false, regionIndex: null };
  }

  for (const [regionIndex, region] of regions.entries()) {
    if (
      !region ||
      !["x", "y", "w", "h"].every((key) => Number.isFinite(region[key]))
    ) {
      continue;
    }
    const left = Math.max(0, region.x - tolerance);
    const top = Math.max(0, region.y - tolerance);
    const right = Math.min(100, region.x + region.w + tolerance);
    const bottom = Math.min(100, region.y + region.h + tolerance);
    if (left <= x && x <= right && top <= y && y <= bottom) {
      return { hit: true, regionIndex };
    }
  }
  return { hit: false, regionIndex: null };
}

export function validateHotspot(regions, tolerance) {
  const errors = [];
  const warnings = [];
  if (!Array.isArray(regions) || !regions.length) {
    errors.push("At least one region is required.");
    return { errors, warnings };
  }
  if (regions.length > 50) {
    errors.push("A maximum of 50 regions is allowed.");
    return { errors, warnings };
  }
  if (
    !Number.isFinite(tolerance) ||
    tolerance < 0 ||
    tolerance > 10
  ) {
    errors.push("Tolerance must be between 0 and 10.");
    tolerance = 0;
  }

  const validRegions = [];
  regions.forEach((region, index) => {
    if (
      !region ||
      !["x", "y", "w", "h"].every((key) => Number.isFinite(region[key]))
    ) {
      errors.push(`Region ${index + 1} needs numeric x, y, w, and h.`);
      return;
    }
    if (region.x < 0 || region.x > 100 || region.y < 0 || region.y > 100) {
      errors.push(`Region ${index + 1} must start within the image.`);
      return;
    }
    if (region.w <= 0 || region.h <= 0) {
      errors.push(`Region ${index + 1} must have positive width and height.`);
      return;
    }
    if (region.x + region.w > 100 || region.y + region.h > 100) {
      errors.push(`Region ${index + 1} extends outside the image.`);
      return;
    }
    const paddedWidth =
      Math.min(100, region.x + region.w + tolerance) -
      Math.max(0, region.x - tolerance);
    const paddedHeight =
      Math.min(100, region.y + region.h + tolerance) -
      Math.max(0, region.y - tolerance);
    if (Math.min(paddedWidth, paddedHeight) < 2) {
      warnings.push(
        `Region ${index + 1} is very small and may be hard to tap on a phone.`,
      );
    }
    validRegions.push({
      left: Math.max(0, region.x - tolerance),
      right: Math.min(100, region.x + region.w + tolerance),
      top: Math.max(0, region.y - tolerance),
      bottom: Math.min(100, region.y + region.h + tolerance),
    });
  });

  if (validRegions.length) {
    const xEdges = [
      ...new Set(validRegions.flatMap(({ left, right }) => [left, right])),
    ].sort((a, b) => a - b);
    let area = 0;
    for (let edgeIndex = 0; edgeIndex < xEdges.length - 1; edgeIndex += 1) {
      const left = xEdges[edgeIndex];
      const right = xEdges[edgeIndex + 1];
      const intervals = validRegions
        .filter((region) => region.left < right && region.right > left)
        .map(({ top, bottom }) => [top, bottom])
        .sort((a, b) => a[0] - b[0]);
      let coveredY = 0;
      if (intervals.length) {
        let [start, end] = intervals[0];
        for (const [top, bottom] of intervals.slice(1)) {
          if (top > end) {
            coveredY += end - start;
            [start, end] = [top, bottom];
          } else {
            end = Math.max(end, bottom);
          }
        }
        coveredY += end - start;
      }
      area += (right - left) * coveredY;
    }
    const coverage = area / 100;
    if (coverage > 25) {
      warnings.push(
        `Regions cover ${Math.round(coverage)}% of the image; random clicks may succeed.`,
      );
    }
  }
  return { errors, warnings };
}

export function formatPercent(value) {
  return Number(value.toFixed(1)).toString();
}
