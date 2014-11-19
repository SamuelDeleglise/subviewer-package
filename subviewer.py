from PyQt4 import QtCore, QtGui
from datetime import datetime, timedelta
import codecs
import re
import sys
#import bisect



            
        


class Item:
    sort_by_begin = True
    def __init__(self, begin, end, text):
        self.begin = begin
        self.end  = end
        self.text = text

    def __lt__(self, other):
        if self.sort_by_begin:
            return self.begin < other.begin

    def to_us(self, time):
        return time.microsecond + 1000000*(time.second + 60*(time.minute + 60*time.hour))

    def __repr__(self):
        st = '====' + str(self.begin) + '---->' + str(self.end) + '============\n' 
        return st + self.text.encode('ASCII', 'ignore')

    @property
    def begin_us(self):
        return self.to_us(self.begin)

    @property
    def end_us(self):
        return self.to_us(self.end)

    
class CircularList:
    def __init__(self, val):
        self.items = val
        self.cursor = 0
        self.n = len(self.items)

    def __iter__(self):
        for val in range(self.n):
            yield self.items[(self.cursor + val)%self.n]

    def __getitem__(self, n):
        return self.items[(self.cursor + n)%self.n]

    def fill_gaps(self):
        last_end_us = 0
        last_end = datetime.strptime('00/1/1','%y/%m/%d')
        for index, item in enumerate(self.items):
            if item.begin_us>last_end_us:
                new_item = Item(last_end, item.begin, "")
                self.items.insert(index, new_item)
            last_end_us = item.end_us
            last_end = item.end
        self.n = len(self.items)

    def current(self):
        return self.items[(self.cursor)%self.n]

    def next(self):
        self.cursor = (self.cursor + 1)%self.n
        return self.items[self.cursor]

    def previous(self):
        self.cursor = (self.cursor - 1)%self.n
        return self.items[self.cursor]    


class TimeDisplayWidget(QtGui.QWidget):
    value_changed = QtCore.pyqtSignal()
    def __init__(self, parent=None):
        super(TimeDisplayWidget, self).__init__(parent)    
        self.layout=QtGui.QHBoxLayout()
        self.clock_seconds = QtGui.QSpinBox()
        self.clock_minutes = QtGui.QSpinBox()
        self.clock_hours = QtGui.QSpinBox()

        self.clock_seconds.valueChanged.connect(self.value_changed)
        self.clock_minutes.valueChanged.connect(self.value_changed)
        self.clock_hours.valueChanged.connect(self.value_changed)
        
        for wid in [self.clock_hours, self.clock_minutes, self.clock_seconds]:
            self.layout.addWidget(wid)
        self.setLayout(self.layout)

    def get_time_us(self):
        return 1000000*(self.clock_seconds.value() + 60*(self.clock_minutes.value() + 60*self.clock_hours.value()))

    def set_time_us(self, time_s):
        self.clock_seconds.setValue(time_s%60)
        self.clock_minutes.setValue((time_s%3600)/60)
        self.clock_hours.setValue(time_s/3600)
        

    
class SyncPointWidget(QtGui.QWidget):
    value_changed = QtCore.pyqtSignal()
    
    def __init__(self, parent=None):
        super(SyncPointWidget, self).__init__(parent)    
        self.layout=QtGui.QHBoxLayout()
        self.clock_video = TimeDisplayWidget()
        self.now_button = QtGui.QPushButton('set as now')
        self.now_button.clicked.connect(self.goto_current)
        self.clock_sub = TimeDisplayWidget()
        self.clock_sub.value_changed.connect(self.value_changed)
        self.clock_video.value_changed.connect(self.value_changed)
        
        self.arrow_label = QtGui.QLabel('-->')
        for wid in [self.clock_sub, self.now_button, self.arrow_label, self.clock_video]:
            self.layout.addWidget(wid)
        self.setLayout(self.layout)

    def goto_current(self):
        self.clock_sub.set_time_us(self.parent().subviewer.timer.current_time/1000000)

class SaveWidget(QtGui.QWidget):
    def __init__(self, subviewer, parent=None):
        super(SaveWidget, self).__init__(parent)    
        self.layout = QtGui.QVBoxLayout(self)
        self.point1 = SyncPointWidget()
        self.point2 = SyncPointWidget()
        self.button_OK = QtGui.QPushButton('OK')
        self.button_OK.clicked.connect(self.save)

        self.point1.value_changed.connect(self.display_gain_offset)
        self.point2.value_changed.connect(self.display_gain_offset)
        self.label_gain_offset = QtGui.QLabel('gain:       offset:    ')
        self.layout.addWidget(self.label_gain_offset)
        
        for wid in [self.point1, self.point2, self.button_OK]:
            self.layout.addWidget(wid)
            
        self.setLayout(self.layout)
        self.subviewer = subviewer
        self.setWindowTitle('Define 2 points of synchro')

        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

    def display_gain_offset(self):
        try:
            gain, offset = self.get_gain_offset()
        except ZeroDivisionError:
            text = "gain: undefined  offset: undefined"
        else:
            text = "gain: %.3f"%gain + "   offset (s): %.3f"%(offset*1./1000000)
        self.label_gain_offset.setText(text)

    def get_gain_offset(self):
        video1 = self.point1.clock_video.get_time_us()
        video2 = self.point2.clock_video.get_time_us()
        sub1 = self.point1.clock_sub.get_time_us()
        sub2 = self.point2.clock_sub.get_time_us()
        gain = (video2 - video1)*1./(sub2 - sub1)
        offset = video1 - gain*sub1
        return gain, offset

    def save(self):
        filename = str(QtGui.QFileDialog.getSaveFileName())
        if filename!="":
            gain_offset = self.get_gain_offset()
            self.subviewer.save(filename, gain_offset)
        self.hide()

class TimerUpdate(QtCore.QTimer):
    def __init__(self, parent=None, timer_interval=300):
        super(TimerUpdate, self).__init__(parent)
        self.current_time = 0
        self.timer_interval = timer_interval
        self.setInterval(timer_interval)
        self.timeout.connect(self.update)
        self.setSingleShot(False)
        self.speed_time = 1.
        self.system_time = QtCore.QTime()

    def start(self):
        super(TimerUpdate, self).start()
        self.system_time.start()
        
    def update(self):
        time_interval = self.system_time.restart()
        new_time = int(self.current_time + time_interval*1000*self.speed_time)
        self.parent().move_to(new_time)
        
        #self.parent().display()

    def go_slower(self, factor=0.001):
        self.speed_time-=factor

    def go_faster(self, factor=0.001):
        self.speed_time+=factor
"""
class SyncWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        super(SyncWidget, self).__init__(parent)
        self.layout = QtGui.QVBoxLayout()
        
        self.button_10min = QtGui.QPushButton("sync 10 min.")
        self.button_40min = QtGui.QPushButton("sync 40 min.")
        self.layout.addWidget(self.button_10min)
        self.layout.addWidget(self.button_40min)
        self.button_10min.clicked.connect(self.sync_10min)
        self.button_40min.clicked.connect(self.sync_40min)
        self.setLayout(self.layout)
        
    def sync_10min(self):
        self.time_10min = self.parent().parent().timer.current_time
        
        
    def sync_40min(self):
        self.time_40min = self.parent().parent().timer.current_time
"""     

class ControlWidget(QtGui.QWidget):
    start_clicked = QtCore.pyqtSignal()
    stop_clicked = QtCore.pyqtSignal()
    faster_clicked = QtCore.pyqtSignal()
    slower_clicked = QtCore.pyqtSignal()
    editing_finished = QtCore.pyqtSignal()
    def __init__(self, parent=None):
        super(ControlWidget, self).__init__(parent)
        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)
        self.start_button = QtGui.QPushButton('Start')
        self.stop_button = QtGui.QPushButton('Pause')
        self.restart_button = QtGui.QPushButton('Reset')
        self.faster_button = QtGui.QPushButton('Faster')
        self.slower_button = QtGui.QPushButton('Slower')
        self.clock_seconds = QtGui.QSpinBox()
        self.clock_minutes = QtGui.QSpinBox()
        self.clock_hours = QtGui.QSpinBox()
#        self.label = QtGui.QLabel("stopped x1.0")
        self.layout.addWidget(self.start_button)
        self.layout.addWidget(self.stop_button)
        self.layout.addWidget(self.restart_button)
        next_action = QtGui.QAction(self)
        next_action.setShortcut(QtCore.Qt.Key_Right)
        next_action.triggered.connect(self.next)
        previous_action = QtGui.QAction(self)
        previous_action.setShortcut(QtCore.Qt.Key_Left)
        previous_action.triggered.connect(self.previous)
        self.addAction(next_action)
        self.addAction(previous_action)

        

        self.spacebar_toggle = QtGui.QAction(self)
        self.spacebar_toggle.setShortcut(QtCore.Qt.Key_Space)
        self.addAction(self.spacebar_toggle)
        self.spacebar_toggle.triggered.connect(self.toggle)
        

        self.layout.addWidget(self.clock_hours)
        self.layout.addWidget(self.clock_minutes)
        self.layout.addWidget(self.clock_seconds)

#       self.layout.addWidget(self.label)
        self.layout.addWidget(self.slower_button)
        self.layout.addWidget(self.faster_button)

        self.start_button.setMinimumWidth(310)
        self.start_button.setMaximumWidth(310)

        
        self.start_button.clicked.connect(self.start_clicked)
        self.start_button.clicked.connect(self.update_label)
        self.stop_button.clicked.connect(self.stop_clicked)
        self.stop_button.clicked.connect(self.update_label)
        self.restart_button.clicked.connect(self.restart)

        self.slower_button.clicked.connect(self.slower_clicked)
        self.faster_button.clicked.connect(self.faster_clicked)
        self.faster_button.clicked.connect(self.update_label)
        self.slower_button.clicked.connect(self.update_label)

        self.faster_button.setAutoRepeat(True)
        self.slower_button.setAutoRepeat(True)

        self.action_faster = QtGui.QAction(self)
        self.action_slower = QtGui.QAction(self)
        self.action_forward = QtGui.QAction(self)
        self.action_backward = QtGui.QAction(self)

        self.action_faster.setShortcut(QtCore.Qt.Key_F)
        self.action_slower.setShortcut(QtCore.Qt.Key_S)
        self.action_forward.setShortcut(QtCore.Qt.Key_Up)
        self.action_backward.setShortcut(QtCore.Qt.Key_Down)

        self.addAction(self.action_faster)
        self.addAction(self.action_slower)
        self.addAction(self.action_forward)
        self.addAction(self.action_backward)

        
        self.action_forward.triggered.connect(self.clock_seconds.stepUp)
        self.action_backward.triggered.connect(self.clock_seconds.stepDown)
        self.action_slower.triggered.connect(self.slower_button.click)
        self.action_faster.triggered.connect(self.faster_button.click)
        
        
        self.clock_seconds.editingFinished.connect(self.editing_finished)
        self.clock_seconds.valueChanged.connect(self.editing_finished)
        self.clock_minutes.editingFinished.connect(self.editing_finished)
        self.clock_minutes.valueChanged.connect(self.editing_finished)
        self.clock_hours.editingFinished.connect(self.editing_finished)
        self.clock_hours.valueChanged.connect(self.editing_finished)

        height = 60
        width = 80
        font = QtGui.QFont('Times', 25)
        self.clock_seconds.setMinimumHeight(height)
        self.clock_seconds.setMaximumWidth(width)
        self.clock_seconds.setFont(font)

        self.clock_minutes.setMinimumHeight(height)
        self.clock_minutes.setMaximumWidth(width)
        self.clock_minutes.setFont(font)

        self.clock_hours.setMinimumHeight(height)
        self.clock_hours.setMaximumWidth(width)
        self.clock_hours.setFont(font)

        self.faster_button.setFont(font)
        self.slower_button.setFont(font)
        self.start_button.setFont(font)       
        self.stop_button.setFont(font)
#        self.label.setFont(font)
        self.restart_button.setFont(font)

        self.save_button = QtGui.QPushButton("Save")
        self.layout.addWidget(self.save_button)
        self.save_button.setFont(font)
        

        self.help_button = QtGui.QPushButton("Help")
        self.help_button.setFont(font)
        self.help_button.clicked.connect(self.show_help)
        self.layout.addWidget(self.help_button)
        self.save_button.clicked.connect(self.save)
        self.save_widget = SaveWidget(subviewer=self.parent())

    def save(self):
        self.save_widget.show()
        

        
    def show_help(self):
        help_msg = """
1. Drag a valid .sub file in the window to load the subtitles
2. Press left / right arrow to browse through subtitles
3. Press space to toggle play / pause
4. s / f to adjust the speed of subtitle display
5. up / down to shift by +/- 1 second
        """
        QtGui.QMessageBox.information(self,
                                      'Help for subviewer',
                                      help_msg,
                                      'OK')

    def toggle(self):
        if self.start_button.isEnabled():
            self.start_button.click()
        else:
            self.stop_button.click()

    def restart(self):
        self.parent().set_time(0)
    
    def update_label(self):
        lab = 'Play    x'
        if self.parent().timer.isActive():
            lab = 'Playing x'
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(self.parent().input_subs is not None)
        else:
            self.start_button.setEnabled(self.parent().input_subs is not None)
            self.stop_button.setEnabled(False)
        lab+="%.3f"%(self.parent().timer.speed_time)
        self.start_button.setText(lab)

    def next(self):
        self.parent().next()

    def previous(self):
        self.parent().previous()
            
class SubViewer(QtGui.QWidget):
    def __init__(self, parent=None, input_subs=None):
        super(SubViewer, self).__init__(parent)
        self.layout = QtGui.QVBoxLayout()
        self.label = QtGui.QTextEdit(self)
        self.label.setReadOnly(True)
        self.layout.addWidget(self.label)
        self.control_widget = ControlWidget(self)
        self.layout.addWidget(self.control_widget)
        
        
        self.label.setFont(QtGui.QFont('Times', 55))
        self.display('Welcome to sub_viewer')
        self.setLayout(self.layout)
        self.show()
        self.timer = TimerUpdate(self)
        self.control_widget.start_clicked.connect(self.timer.start)
        self.control_widget.stop_clicked.connect(self.timer.stop)
        self.control_widget.slower_clicked.connect(self.timer.go_slower)
        self.control_widget.faster_clicked.connect(self.timer.go_faster)

        self.control_widget.editing_finished.connect(self.update_time)
        self.setAcceptDrops(True)

        self.set_file(input_subs)

    def linear_transf(self, date, gain, offset):
        date_zero = datetime.strptime('00/1/1','%y/%m/%d')


        print gain, offset

        second = 1000000
        minute = second*60
        hour = minute*60
        
        
        hours = offset/hour
        minutes = offset%hour/minute
        seconds = offset%second/second
        
        
        offset_date = timedelta(#hours = (hours),
                           #minutes=(minutes),
                           #seconds=(seconds),
                           microseconds=int(abs(offset)))

        res = date_zero + (date - date_zero)*int(1000000*gain)/1000000
        if offset>0:
            res += offset_date
        else:
            res -= offset_date
        if res>date_zero:
            return res

    def save(self, filename, gain_offset):
        gain, offset = gain_offset
        with codecs.open(filename, "w", "utf-8") as f:#, "utf-8"
            index = 0
            for item in self.items.items:
                if item.text=="":
                    continue
                index+=1

                begin =  self.linear_transf(item.begin, gain, offset)
                end = self.linear_transf(item.end, gain, offset)
                
                if begin is None:
                    continue
                
                f.write(str(index))
                f.write('\r\n')
                f.write(begin.strftime('%H:%M:%S,%f')[:-3])
                f.write(' --> ')
                f.write(end.strftime('%H:%M:%S,%f')[:-3])
                f.write('\r\n')
                f.write(item.text)
                #f.write('\r\n')

    def goto_item(self, item):
        self.timer.current_time = item.begin_us + 1
        self.display_time(self.timer.current_time/1000000)
        self.display(item.text)

    def next(self):
        item = self.items.next()
        self.goto_item(item)
        
    def previous(self):
        item = self.items.previous()
        self.goto_item(item)

    def update_time(self):
        self.set_time(self.get_time())

    def display_time(self, time_s):
        self.control_widget.blockSignals(True)
        self.control_widget.clock_seconds.setValue(time_s%60)
        self.control_widget.clock_minutes.setValue((time_s%3600)/60)
        self.control_widget.clock_hours.setValue(time_s/3600)
        self.control_widget.blockSignals(False)
        
    def set_time(self, time_s):
        #self.display_time(time_s)
        #self.timer.current_time = time_s*1000000
        self.move_to(time_s)

    def get_time(self):
        return 1000000*(self.control_widget.clock_seconds.value() + \
                     60*(self.control_widget.clock_minutes.value() +\
                         60*self.control_widget.clock_hours.value()))
    

    def set_file(self, input_subs):
        self.input_subs = input_subs
        if self.input_subs is None:
            self.setWindowTitle('Subviewer... Drag a sub file in this window')
        else:
            try:
                self.parse_subs()
            except Exception as e:
                print e
                self.setWindowTitle('File: ' + input_subs + ' could not be parsed... try another one.')
                self.input_subs = None
            else:
                self.setWindowTitle('Viewing: ' + input_subs)
        self.control_widget.update_label()
    
    def display(self, string):
        self.label.setText(string)

    def sizeHint(self):
        return QtCore.QSize(1400, 600)

    def parse_subs(self):
        self.items = []
        last_item = Item(0,1, 'Welcome')
        encoding = 'utf-8'
        try:
            with codecs.open(self.input_subs, 'r', encoding=encoding) as f:
                f.read()
        except UnicodeDecodeError:
            encoding = 'ISO-8859-1'
        with codecs.open(self.input_subs, 'r', encoding=encoding, errors='ignore') as input:
            nsafe = lambda s: int(s) if s else 0
            block = 0
            date_zero = datetime.strptime('00/1/1','%y/%m/%d')
            for line in input:
                try:
                    int(line)
                except ValueError:
                    pass
                else:
                    continue
                parsed = re.search('(\d{2}:\d{2}:\d{2},\d{3}) \-\-> (\d{2}:\d{2}:\d{2},\d{3})', line)
                if parsed:
                    block += 1
                    start, end = (self.parse_time(parsed.group(1)), self.parse_time(parsed.group(2)))
                    last_item = Item(start, end, "")
                    self.items.append(last_item)
                else:
                    last_item.text+=line

        self.items = CircularList(self.items)
        self.items.fill_gaps()
#                    output.write('%s --> %s\n' % (offset_start, offset_end))
#                else:
#                    output.write(line)

    def parse_time(self, time):
        parsed = datetime.strptime(time, '%H:%M:%S,%f')
        return parsed.replace(year=2000)



    def move_to(self, time_us):
        self.timer.current_time = time_us
        if time_us/1000000!=self.get_time():
            self.display_time(time_us/1000000)
        for index, item in enumerate(self.items):
            if item.begin_us < time_us:
                if item.end_us > time_us:
                    self.items.cursor = (self.items.cursor + index)%self.items.n
                    self.display(item.text)
                    return item.text
        print 'nothing found'
        return ""
                

    def dragEnterEvent(self, drop_event):
        if len(drop_event.mimeData().urls())!=1:
            drop_event.reject()
        else:
            drop_event.accept()
    def dropEvent(self, drop_event):
        path = str(drop_event.mimeData().urls()[0].path())
        if path[2]==':' and path[0]=='/':
            path = path[1:]
        self.set_file(path)



if __name__=='__main__':
    if len(sys.argv)>1:
        arg = sys.argv[1]
    else:
        arg = None
    APP = QtGui.QApplication([])
    print arg
    SUBVIEWER = SubViewer(input_subs=arg)
    APP.exec_()
