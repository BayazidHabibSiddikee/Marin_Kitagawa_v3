import { apiClient } from '../apiClient';

export function analyzeYoutube(url: string) {
  return apiClient.fetch(url);
}
