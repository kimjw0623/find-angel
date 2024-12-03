import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

class ApiClient {
  constructor(baseURL = API_BASE_URL) {
    this.client = axios.create({
      baseURL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // 응답 인터셉터 추가
    this.client.interceptors.response.use(
      (response) => response.data,
      (error) => {
        console.error('API Error:', error.response?.data || error.message);
        throw error;
      }
    );
  }

  // 가격 추이 데이터 조회
  async getPriceTrends(params = {}) {
    const { role, grade, part, timeRange = '1d' } = params;
    try {
      const queryParams = new URLSearchParams();
      if (role) queryParams.append('role', role);
      if (grade) queryParams.append('grade', grade);
      if (part) queryParams.append('part', part);
      queryParams.append('time_range', timeRange);

      return await this.client.get(`/price-trends?${queryParams.toString()}`);
    } catch (error) {
      console.error('Failed to fetch price trends:', error);
      throw error;
    }
  }

  // 인기 패턴 조회
  async getAllPatterns() {
    try {
      return await this.client.get('/all-patterns');
    } catch (error) {
      console.error('Failed to fetch all patterns:', error);
      throw error;
    }
  }

  // 특정 패턴의 상세 정보 조회
  async getPatternDetails(patternKey, timeRange = '1d') {
    try {
      return await this.client.get(`/all-patterns/${patternKey}`, {
        params: { time_range: timeRange }
      });
    } catch (error) {
      console.error('Failed to fetch pattern details:', error);
      throw error;
    }
  }

    // 팔찌 가격 추이 데이터 조회
  async getBraceletTrends(params = {}) {
    const { grade, timeRange = '1d' } = params;
    try {
      const queryParams = new URLSearchParams();
      if (grade) queryParams.append('grade', grade);
      queryParams.append('time_range', timeRange);

      return await this.client.get(`/bracelet-trends?${queryParams.toString()}`);
    } catch (error) {
      console.error('Failed to fetch bracelet trends:', error);
      throw error;
    }
  }

  // 팔찌 패턴 데이터 조회
  async getBraceletPatterns(params = {}) {
    const { grade } = params;
    try {
      const queryParams = new URLSearchParams();
      if (grade) queryParams.append('grade', grade);

      return await this.client.get(`/bracelet-patterns?${queryParams.toString()}`);
    } catch (error) {
      console.error('Failed to fetch bracelet patterns:', error);
      throw error;
    }
  }

  // 데이터 다운로드 (CSV 형식)
  async exportData(params = {}) {
    try {
      const response = await this.client.get('/export', {
        params,
        responseType: 'blob'
      });
      
      const blob = new Blob([response], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `market-data-${new Date().toISOString()}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error('Failed to export data:', error);
      throw error;
    }
  }

  // 에러 처리를 위한 유틸리티 메서드
  handleError(error) {
    if (error.response) {
      // 서버 응답이 있는 경우
      const { status, data } = error.response;
      switch (status) {
        case 404:
          return { error: 'Requested data not found' };
        case 400:
          return { error: data.detail || 'Invalid request' };
        case 500:
          return { error: 'Server error occurred' };
        default:
          return { error: 'Unknown error occurred' };
      }
    }
    // 네트워크 에러 등
    return { error: 'Network error occurred' };
  }
}

// API 클라이언트 인스턴스 생성
const api = new ApiClient();

export default api;