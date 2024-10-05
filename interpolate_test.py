# import numpy as np
# import matplotlib.pyplot as plt
# from scipy import interpolate
# from sklearn.isotonic import IsotonicRegression

# def monotonic_spline(x, y, num_points=1000):
#     # 데이터 정렬
#     sort_idx = np.argsort(x)
#     x_sorted = x[sort_idx]
#     y_sorted = y[sort_idx]
    
#     # Isotonic Regression 적용
#     ir = IsotonicRegression(out_of_bounds='clip')
#     y_iso = ir.fit_transform(x_sorted, y_sorted)
    
#     # UnivariateSpline을 사용하여 부드러운 곡선 생성
#     spl = interpolate.UnivariateSpline(x_sorted, y_iso, s=len(x_sorted) * 0.1)
    
#     # 보간된 점 생성
#     x_interp = np.linspace(x_sorted.min(), x_sorted.max(), num_points)
#     y_interp = spl(x_interp)
    
#     return x_interp, y_interp

# # 예제 데이터 생성 (완벽하게 단조 증가하지 않음)
# np.random.seed(0)
# x = np.sort(np.random.rand(20) * 10)
# y = np.cumsum(np.random.rand(20)) + np.random.randn(20) * 0.5

# # 단조 증가 스플라인 적용
# x_monotonic, y_monotonic = monotonic_spline(x, y)

# # 결과 시각화
# plt.figure(figsize=(12, 6))
# plt.scatter(x, y, c='red', label='Original data')
# plt.plot(x_monotonic, y_monotonic, 'b-', label='Monotonic Spline')

# plt.xlabel('X')
# plt.ylabel('Y')
# plt.title('Monotonic Spline Interpolation')
# plt.legend()
# plt.grid(True)
# plt.show()

# # 원본 데이터 포인트에서의 interpolated 값 계산
# y_interpolated = np.interp(x, x_monotonic, y_monotonic)

# # RMSE 계산
# rmse = np.sqrt(np.mean((y - y_interpolated)**2))
# print(f"RMSE: {rmse}")

# # 단조 증가 확인
# is_monotonic = np.all(np.diff(y_monotonic) >= 0)
# print(f"Is monotonically increasing: {is_monotonic}")

from datetime import datetime, timedelta
from utils import *
evaluate_functions = load_evaluate_functions()

current_time = datetime.now()
if (datetime.strptime(evaluate_functions["time"], "%Y-%m-%d %H:%M:%S") < current_time - timedelta(minutes=30)):  
    print("go")
else:
    print("go anyway")