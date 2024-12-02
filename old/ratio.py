import matplotlib.pyplot as plt
import numpy as np

# 기본 설정
min_ratio = 0.5  # 최소 비율 (50%)
max_ratio = 0.75  # 최대 비율 (80%)
max_price = 200000

# 수동으로 지정한 점들 (x: expected_price, y: current_price)
manual_points = [
    (10000, 5000), 
    (70000, 40000),  
    (100000, 60000), 
    (150000, 100000),
    (200000, 140000),
    (300000, 220000),
    (400000, 300000),
]
manual_x, manual_y = zip(*manual_points)

# 그래프 생성
plt.figure(figsize=(12, 8))

# 최소/최대 비율 직선
plt.plot([0, 2*max_price], [0, 2*max_price * min_ratio], 'k:', alpha=0.5, label=f'Min Ratio ({min_ratio:.0%})')
plt.plot([0, 2*max_price], [0, 2*max_price * max_ratio], 'k:', alpha=0.5, label=f'Max Ratio ({max_ratio:.0%})')

# 기존 모델들 그리기
x = np.linspace(0, 2*max_price, 1000)

# 원래 sigmoid
k1 = 5e-5
midpoint1 = max_price/3
sigmoid_ratio1 = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k1 * (x - midpoint1)))
plt.plot(x, x * sigmoid_ratio1, 'g-', label='Original Sigmoid', alpha=0.7)

# 조정된 sigmoid들
# k2 = 3e-5  # 더 완만한 기울기
# midpoint2 = max_price/2  # 더 늦은 변곡점
# sigmoid_ratio2 = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k2 * (x - midpoint2)))
# plt.plot(x, x * sigmoid_ratio2, 'b-', label='Adjusted Sigmoid 1', alpha=0.7)

k3 = 3e-5  # 가장 완만한 기울기
midpoint3 = max_price*2/3  # 가장 늦은 변곡점
sigmoid_ratio3 = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k3 * (x - midpoint3)))
plt.plot(x, x * sigmoid_ratio3, 'r-', label='Adjusted Sigmoid 2', alpha=0.7)

y = np.linspace(0, 2*max_price, 41)
sigmoid_ratio4 = min_ratio + (max_ratio - min_ratio) / (1 + np.exp(-k3 * (y - midpoint3)))
for i in range(len(y)):
    print(y[i], (y * sigmoid_ratio4)[i])

# 수동 점들과 선 그리기
plt.plot(manual_x, manual_y, 'bo-', label='Manual', linewidth=2)  # 파란 점과 선
plt.plot(manual_x, manual_y, 'bo')  # 점을 더 강조

# y = x 참조선
plt.plot([0, 2*max_price], [0, 2*max_price], 'k--', alpha=0.3, label='y = x')

# 그래프 설정
plt.xlabel('Expected Price (Gold)')
plt.ylabel('Current Price (Gold)')
plt.title('Threshold Models with Manual Points')
plt.grid(True, linestyle='--', alpha=0.3)
plt.legend()
plt.tight_layout()
plt.show()