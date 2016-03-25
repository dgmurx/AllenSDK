import scipy.stats as st
import numpy as np
import pandas as pd
import os
import time
from allensdk.cam.findlevel import findlevel

class OPAnalysis(object):
    def __init__(self, cam_analysis,
                 **kwargs):
        self.cam_analysis = cam_analysis

        self.meta_data = self.cam_analysis.nwb.get_meta_data()
        self.Cre = self.meta_data['Cre']
        self.HVA = self.meta_data['area']
        self.specimen = self.meta_data['specimen']
        self.experiment_id = self.meta_data['experiment_id']
        print "Cre line:", self.Cre
        print "Targeted area:", self.HVA
        print "Specimen:", self.specimen
        
        self.savepath = self.cam_analysis.save_path
        
        self.timestamps, self.celltraces = self.cam_analysis.nwb.get_fluorescence_traces()
        self.numbercells = len(self.celltraces)                         #number of cells in dataset       
        self.acquisition_rate = 1/(self.timestamps[1]-self.timestamps[0])
        self.dxcm, self.dxtime = self.cam_analysis.nwb.get_running_speed()        
#        self.celltraces_dff = self.getGlobalDFF(percentiletosubtract=8)
#        self.binned_dx_sp, self.binned_cells_sp, self.binned_dx_vis, self.binned_cells_vis = self.getSpeedTuning(binsize=400)
    
    def getGlobalDFF(self, percentiletosubtract=8):
        '''does a global DF/F using a sliding window (+/- 15 s) baseline subtraction followed by Fo=peak of histogram'''
        '''replace when DF/F added to nwb file'''        
        print "Calculating global DF/F ... this can take some time"
        startTime = time.time()
        celltraces_dff = np.zeros(self.celltraces.shape)
        for i in range(450):
            celltraces_dff[:,i] = self.celltraces[:,i] - np.percentile(self.celltraces[:,:(i+450)], percentiletosubtract, axis=1)
        for i in range(450, np.size(self.celltraces,1)-450):
            celltraces_dff[:,i] = self.celltraces[:,i] - np.percentile(self.celltraces[:,(i-450):(i+450)], percentiletosubtract, axis=1)
        for i in range(np.size(self.celltraces,1)-450, np.size(self.celltraces,1)):
            celltraces_dff[:,i] = self.celltraces[:,i] - np.percentile(self.celltraces[:,(i-450):], percentiletosubtract, axis=1)

        print "we're still here"
        for cn in range(self.numbercells):
            (val, edges) = np.histogram(celltraces_dff[cn,:], bins=200)
            celltraces_dff[cn,:] /= edges[np.argmax(val)+1]
            celltraces_dff[cn,:] -= 1
            celltraces_dff[cn,:] *= 100
        elapsedTime = time.time() - startTime
        print "Elapsed Time:", str(elapsedTime)
        return celltraces_dff
    
    def getSpeedTuning(self, binsize):
        print 'Calculating speed tuning, spontaneous vs visually driven'
        celltraces_trimmed = np.delete(self.celltraces_dff, range(len(self.dxcm), np.size(self.celltraces_dff,1)), axis=1) 
        #pull out spontaneous epoch(s)        
        spontaneous = self.cam_analysis.nwb.get_stimulus_table('spontaneous')

        peak_run = pd.DataFrame(index=range(self.numbercells), columns=('speed_max_sp','speed_min_sp','ptest_sp', 'mod_sp','speed_max_vis','speed_min_vis','ptest_vis', 'mod_vis'))
        peak_run['ExperimentID'] = self.experiment_id
        peak_run['Cre'] = self.Cre   
        peak_run['HVA'] = self.HVA
        peak_run['depth'] = self.cam_analysis.depth        
        
        dx_sp = self.dxcm[spontaneous.start.iloc[-1]:spontaneous.end.iloc[-1]]
        celltraces_sp = celltraces_trimmed[:,spontaneous.start.iloc[-1]:spontaneous.end.iloc[-1]]
        dx_vis = np.delete(self.dxcm, np.arange(spontaneous.start.iloc[-1],spontaneous.end.iloc[-1]))
        celltraces_vis = np.delete(celltraces_trimmed, np.arange(spontaneous.start.iloc[-1],spontaneous.end.iloc[-1]), axis=1)
        if len(spontaneous) > 1:
            dx_sp = np.append(dx_sp, self.dxcm[spontaneous.start.iloc[-2]:spontaneous.end.iloc[-2]], axis=0)
            celltraces_sp = np.append(celltraces_sp,celltraces_trimmed[:,spontaneous.start.iloc[-2]:spontaneous.end.iloc[-2]], axis=1)
            dx_vis = np.delete(dx_vis, np.arange(spontaneous.start.iloc[-2],spontaneous.end.iloc[-2]))
            celltraces_vis = np.delete(celltraces_vis, np.arange(spontaneous.start.iloc[-2],spontaneous.end.iloc[-2]), axis=1)
        celltraces_vis = celltraces_vis[:,~np.isnan(dx_vis)]
        dx_vis = dx_vis[~np.isnan(dx_vis)]  
        
        nbins = 1 + len(np.where(dx_sp>=1)[0])/binsize
        dx_sorted = dx_sp[np.argsort(dx_sp)]
        celltraces_sorted_sp = celltraces_sp[:, np.argsort(dx_sp)]
        binned_cells_sp = np.zeros((self.numbercells, nbins, 2))
        binned_dx_sp = np.zeros((nbins,2))
        for i in range(nbins):
            offset = findlevel(dx_sorted,1,'up')        
            if i==0:
                binned_dx_sp[i,0] = np.mean(dx_sorted[:offset])
                binned_dx_sp[i,1] = np.std(dx_sorted[:offset])/np.sqrt(offset)           
                binned_cells_sp[:,i,0] = np.mean(celltraces_sorted_sp[:,:offset], axis=1)
                binned_cells_sp[:,i,1] = np.std(celltraces_sorted_sp[:,:offset], axis=1)/np.sqrt(offset)
            else:
                start = offset + (i-1)*binsize
                binned_dx_sp[i,0] = np.mean(dx_sorted[start:start+binsize])
                binned_dx_sp[i,1] = np.std(dx_sorted[start:start+binsize])
                binned_cells_sp[:,i,0] = np.mean(celltraces_sorted_sp[:, start:start+binsize], axis=1)
                binned_cells_sp[:,i,1] = np.std(celltraces_sorted_sp[:,start:start+binsize], axis=1)
        
        binned_cells_shuffled_sp = np.empty((self.numbercells, nbins, 2, 200))
        for shuf in range(200):
            celltraces_shuffled = celltraces_sp[:,np.random.permutation(np.size(celltraces_sp,1))]
            celltraces_shuffled_sorted = celltraces_shuffled[:, np.argsort(dx_sp)]
            for i in range(nbins):
                offset = findlevel(dx_sorted,1,'up')        
                if i==0:          
                    binned_cells_shuffled_sp[:,i,0,shuf] = np.mean(celltraces_shuffled_sorted[:,:offset], axis=1)
                    binned_cells_shuffled_sp[:,i,1,shuf] = np.std(celltraces_shuffled_sorted[:,:offset], axis=1)/np.sqrt(binsize)
                else:
                    start = offset + (i-1)*binsize
                    binned_cells_shuffled_sp[:,i,0,shuf] = np.mean(celltraces_shuffled_sorted[:, start:start+binsize], axis=1)
                    binned_cells_shuffled_sp[:,i,1,shuf] = np.std(celltraces_shuffled_sorted[:,start:start+binsize], axis=1)/np.sqrt(binsize)
                
        nbins = 1 + len(np.where(dx_vis>=1)[0])/binsize
        dx_sorted = dx_vis[np.argsort(dx_vis)]
        celltraces_sorted_vis = celltraces_vis[:, np.argsort(dx_vis)]
        binned_cells_vis = np.zeros((self.numbercells, nbins, 2))
        binned_dx_vis = np.zeros((nbins,2))
        for i in range(nbins):
            offset = findlevel(dx_sorted,1,'up')        
            if i==0:
                binned_dx_vis[i,0] = np.mean(dx_sorted[:offset])
                binned_dx_vis[i,1] = np.std(dx_sorted[:offset])/np.sqrt(offset)            
                binned_cells_vis[:,i,0] = np.mean(celltraces_sorted_vis[:,:offset], axis=1)
                binned_cells_vis[:,i,1] = np.std(celltraces_sorted_vis[:,:offset], axis=1)/np.sqrt(offset)
            else:
                start = offset + (i-1)*binsize
                binned_dx_vis[i,0] = np.mean(dx_sorted[start:start+binsize])
                binned_dx_vis[i,1] = np.std(dx_sorted[start:start+binsize])/np.sqrt(binsize)
                binned_cells_vis[:,i,0] = np.mean(celltraces_sorted_vis[:, start:start+binsize], axis=1)
                binned_cells_vis[:,i,1] = np.std(celltraces_sorted_vis[:,start:start+binsize], axis=1)/np.sqrt(binsize)
        
        binned_cells_shuffled_vis = np.empty((self.numbercells, nbins, 2, 200))
        for shuf in range(200):
            celltraces_shuffled = celltraces_vis[:,np.random.permutation(np.size(celltraces_vis,1))]
            celltraces_shuffled_sorted = celltraces_shuffled[:, np.argsort(dx_vis)]
            for i in range(nbins):
                offset = findlevel(dx_sorted,1,'up')        
                if i==0:          
                    binned_cells_shuffled_vis[:,i,0,shuf] = np.mean(celltraces_shuffled_sorted[:,:offset], axis=1)
                    binned_cells_shuffled_vis[:,i,1,shuf] = np.std(celltraces_shuffled_sorted[:,:offset], axis=1)/np.sqrt(offset)
                else:
                    start = offset + (i-1)*binsize
                    binned_cells_shuffled_vis[:,i,0,shuf] = np.mean(celltraces_shuffled_sorted[:, start:start+binsize], axis=1)
                    binned_cells_shuffled_vis[:,i,1,shuf] = np.std(celltraces_shuffled_sorted[:,start:start+binsize], axis=1)/np.sqrt(binsize)
         
        shuffled_variance_sp = binned_cells_shuffled_sp[:,:,0,:].std(axis=1)**2
        variance_threshold_sp = np.percentile(shuffled_variance_sp, 99.9, axis=1)
        response_variance_sp = binned_cells_sp[:,:,0].std(axis=1)**2

                 
        shuffled_variance_vis = binned_cells_shuffled_vis[:,:,0,:].std(axis=1)**2
        variance_threshold_vis = np.percentile(shuffled_variance_vis, 99.9, axis=1)
        response_variance_vis = binned_cells_vis[:,:,0].std(axis=1)**2
         
        for nc in range(self.numbercells):
            if response_variance_vis[nc]>variance_threshold_vis[nc]:
                peak_run.mod_vis.iloc[nc] = True
            if response_variance_vis[nc]<=variance_threshold_vis[nc]:
                peak_run.mod_vis.iloc[nc] = False
            if response_variance_sp[nc]>variance_threshold_sp[nc]:
                peak_run.mod_sp.iloc[nc] = True
            if response_variance_sp[nc]<=variance_threshold_sp[nc]:
                peak_run.mod_sp.iloc[nc] = False
            temp = binned_cells_sp[nc,:,0]
            start_max = temp.argmax()
            peak_run.speed_max_sp.iloc[nc] = binned_dx_sp[start_max,0]
            start_min = temp.argmin()
            peak_run.speed_min_sp.iloc[nc] = binned_dx_sp[start_min,0]
            if peak_run.speed_max_sp[nc]>peak_run.speed_min_sp[nc]:
                test_values = celltraces_sorted_sp[nc,start_max*binsize:(start_max+1)*binsize]
                other_values = np.delete(celltraces_sorted_sp[nc,:], range(start_max*binsize, (start_max+1)*binsize))
#                (_ ,peak_run.ptest_sp.iloc[nc]) = st.ks_2samp(test_values, other_values)
            else:
                test_values = celltraces_sorted_sp[nc,start_min*binsize:(start_min+1)*binsize]
                other_values = np.delete(celltraces_sorted_sp[nc,:], range(start_min*binsize, (start_min+1)*binsize))
            (_ ,peak_run.ptest_sp.iloc[nc]) = st.ks_2samp(test_values, other_values)
            temp = binned_cells_vis[nc,:,0]
            start_max = temp.argmax()
            peak_run.speed_max_vis.iloc[nc] = binned_dx_vis[start_max,0]
            start_min = temp.argmin()
            peak_run.speed_min_vis.iloc[nc] = binned_dx_vis[start_min,0]
            if peak_run.speed_max_vis[nc]>peak_run.speed_min_vis[nc]:
                test_values = celltraces_sorted_vis[nc,start_max*binsize:(start_max+1)*binsize]
                other_values = np.delete(celltraces_sorted_vis[nc,:], range(start_max*binsize, (start_max+1)*binsize))
            else:  
                test_values = celltraces_sorted_vis[nc,start_min*binsize:(start_min+1)*binsize]
                other_values = np.delete(celltraces_sorted_vis[nc,:], range(start_min*binsize, (start_min+1)*binsize))
            (_ ,peak_run.ptest_vis.iloc[nc]) = st.ks_2samp(test_values, other_values)
        
#        peak_run.to_csv(os.path.join(self.savepath, 'peak_Speed.csv'))
        #TODO: why doesn't this save?  it says the file doesn't exist, but I'm trying to create it here.  Worked in previous version           
        return binned_dx_sp, binned_cells_sp, binned_dx_vis, binned_cells_vis, peak_run

    def getSweepResponse(self):
        '''calculates the response to each sweep and then for each stimulus condition'''
        def domean(x):
            return np.mean(x[self.interlength:self.interlength+self.sweeplength+self.extralength])#+1])
            
        def doPvalue(x):
            (_, p) = st.f_oneway(x[:self.interlength], x[self.interlength:self.interlength+self.sweeplength+self.extralength])
            return p
            
        print 'Calculating responses for each sweep'        
        sweep_response = pd.DataFrame(index=self.stim_table.index.values, columns=np.array(range(self.numbercells+1)).astype(str))
        sweep_response.rename(columns={str(self.numbercells) : 'dx'}, inplace=True)
        for index, row in self.stim_table.iterrows():
            start = row['start'] - self.interlength
            end = row['start'] + self.sweeplength + self.interlength
            for nc in range(self.numbercells):
                temp = self.celltraces[nc,start:end]                                
                sweep_response[str(nc)][index] = 100*((temp/np.mean(temp[:self.interlength]))-1)
            sweep_response['dx'][index] = self.dxcm[start:end]   
        
        mean_sweep_response = sweep_response.applymap(domean)
        
        pval = sweep_response.applymap(doPvalue)
        return sweep_response, mean_sweep_response, pval            
        
#    def testPtest(self):
#        '''running new ptest'''
#        test = pd.DataFrame(index=self.sweeptable.index.values, columns=np.array(range(self.numbercells)).astype(str))
#        for nc in range(self.numbercells):        
#            for index, row in self.sweeptable.iterrows():
#                ori=row['Ori']
#                tf=row['TF']
#                test[str(nc)][index] = self.mean_sweep_response[(self.sync_table['TF']==tf)&(self.sync_table['Ori']==ori)][str(nc)]
#        ptest = []
#        for nc in range(self.numbercells):
#            groups = []
#            for index,row in test.iterrows():
#                groups.append(test[str(nc)][index])
#                (_,p) = st.f_oneway(*groups)
#            ptest.append(p)
#        ptest = np.array(ptest)
#        cells = list(np.where(ptest<0.01)[0])
#        print "# cells: " + str(len(ptest))
#        print "# significant cells: " + str(len(cells))
#        return ptest, cells
#    
#    def Ptest(self):
#        ptest = np.empty((self.numbercells))
#        for nc in range(self.numbercells):
#            groups = []
#            for ori in self.orivals:
#                for tf in self.tfvals:
#                    groups.append(self.mean_sweep_response[(self.stim_table.temporal_frequency==tf)&(self.stim_table.orientation==ori)][str(nc)])
#            _,p = st.f_oneway(*groups)
#            ptest[nc] = p
#        return ptest
