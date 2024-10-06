import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
from sklearn.ensemble import RandomForestRegressor
import json

with open("new_data.json", 'r') as json_file:
    target_data = json.load(json_file)

tot_data = np.array(target_data) # [N,6]
y = tot_data[:,0]
x = tot_data[:,1:]

# 2. 학습 데이터와 테스트 데이터 분리
X_train, X_test, y_train, y_test = train_test_split(x, y, test_size=0.05, random_state=42)

model = RandomForestRegressor()
model.fit(X_train, y_train)
y_pred = model.predict(X_test)

for xt,yp,yt in zip(X_test,y_pred,y_test):
    print(f"Input: {xt} | GT: {yt:07d} | Pred: {int(yp):07d} | Subs: {(yt-yp)/yp*100:.2f}")
