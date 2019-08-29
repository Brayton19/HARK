#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Consumption-Saving model with Endogenous Labor Supply Model - Intensive Margin
using the endogenous grid method to invert the first order condition.

To solve this agent's problem, we normalized the problem by p_t, the permanent
productivity level, which helps us to eliminate a state variable (p_t).
We can then transform the agent's problem into a cost minimization problem for 
which we solve the effective consumption purchased, x_t= z_t^alpha * c_t
It allows us to solve only one FOC with respect to x_t, instead of 2.

We can then solve the FOC using the Endogenous Gridpoint Method, EGM. 
Faster solution method than the classic rootfinding method but we should keep 
in mind that the EGM solution is not well behaved outside the range of 
gridpoints selected. 

@author: Tiphanie Magne
University of Delaware
"""
import sys 
import os
sys.path.insert(0, os.path.abspath('../'))
sys.path.insert(0, os.path.abspath('./'))

from copy import copy
import numpy as np
from HARK.core import Solution
from HARK.utilities import CRRAutilityP, CRRAutilityP_inv
from HARK.interpolation import LinearInterp, LinearInterpOnInterp1D, VariableLowerBoundFunc2D, BilinearInterp, ConstantFunction
from HARK.ConsumptionSaving.ConsIndShockModel import IndShockConsumerType, MargValueFunc
from HARK.ConsumptionSaving.ConsGenIncProcessModel import ValueFunc2D, MargValueFunc2D

class ConsumerLaborSolution(Solution):
    '''
    A class for representing one period of the solution to a Consumer Labor problem.
    '''
    distance_criteria = ['cFunc','LbrFunc']
    
    def __init__(self,cFunc=None,LbrFunc=None,vFunc=None,vPfunc=None,bNrmMin = None):
        '''
        The constructor for a new ConsumerSolution object.
        
        Parameters
        ----------
        cFunc : function
            The consumption function for this period, defined over bank balances: c = cFunc(b).
        LbrFunc : function
            The labor function for this period, defined over bank balances: l = LbrFunc(b).
        vFunc : function
            The beginning-of-period marginal value function for this period, defined over
            bank balances: v = vPfunc(b).
        vPfunc : function
            The beginning-of-period marginal value function for this period, defined over
            bank balances: v = vPfunc(b).
        bNrmMin: float
            The minimum allowable bank balances for this period. Consumption function,
            labor function etc. are undefined for b < bNrmMin.
            
        '''
        if cFunc is not None:
            setattr(self,'cFunc',cFunc)
        if LbrFunc is not None:
            setattr(self,'LbrFunc',LbrFunc)
        if vFunc is not None:
            setattr(self,'vFunc',vFunc)
        if vPfunc is not None:
            setattr(self,'vPfunc',vPfunc)
        if bNrmMin is not None:
            setattr(self,'bNrmMin',bNrmMin)


def solveConsLaborIntMarg(solution_next,PermShkDstn,TranShkDstn,LivPrb,DiscFac,CRRA,
                          Rfree,PermGroFac,BoroCnstArt,aXtraGrid,TranShkGrid,vFuncBool,
                          CubicBool,WageRte,LbrCost):
    '''
    Solves one period of the consumption-saving model with endogenous labor supply on the intensive margin
    by using the endogenous grid method to invert the first order condition, obviating any search.
    
    Parameters 
    ----------
    solution_next : ConsumerLaborSolution
        The solution to the next period's problem; should have the attributes
        vPfunc, cFunc and LbrFunc representing the marginal value, consumption 
        and labor functions.
 
    PermShkDstn: [np.array]
        Discrete distribution of permanent productivity shocks. 
    TranShkDstn: [np.array]
        Discrete distribution of transitory productivity shocks.       
    LivPrb : float
        Survival probability; likelihood of being alive at the beginning of
        the succeeding period. 
    DiscFac : float
        Intertemporal discount factor.
    CRRA : float
        Coefficient of relative risk aversion.  
    Rfree : float
        Risk free interest rate on assets retained at the end of the period.
    PermGroFac : float                                                         
        Expected permanent income growth factor for next period.
    BoroCnstArt: float or None
        Borrowing constraint for the minimum allowable assets to end the
        period with.  If it is less than the natural borrowing constraint,
        then it is irrelevant; BoroCnstArt=None indicates no artificial bor-
        rowing constraint.
    aXtraGrid: [np.array]
        Array of "extra" end-of-period asset values-- assets above the
        absolute minimum acceptable level.
    TranShkGrid: [np.array]
            Array of transitory shock values.
    vFuncBool: boolean
        An indicator for whether the value function should be computed and
        included in the reported solution.
    CubicBool: boolean
        An indicator for whether the solver should use cubic or linear inter-
        polation.
    WageRte: float
        Wage rate. To be specified by the user.
    LbrCost: float
        alpha parameter indicating labor cost.
        
    Returns
    -------
    solution_now : ConsumerLaborSolution
        The solution to this period's problem, including a consumption
            function cFunc (defined over the bank balances and the transitory 
            productivity shock), a labor function LbrFunc and a marginal value 
            function vPfunc.
    '''
    frac = 1./(1.+LbrCost)

    if CRRA <= frac*LbrCost:
        print ' Error: make sure CRRA coefficient is strictly greater than alpha/(1+alpha).' 
#        return None 
        sys.exit()     
    if BoroCnstArt is not None:
        print ' Error: Model that cannot handle artificial borrowing constraint yet. '
        return None
    if vFuncBool or CubicBool is True:
        print ' Error: Model that cannot handle Cubic interpolation yet.'
        return None

    # Unpack next period's solution and the productivity shock distribution, and define the inverse (marginal) utilty function
    vPfunc_next = solution_next.vPfunc
    TranShkPrbs = TranShkDstn[0]    
    TranShkVals  = TranShkDstn[1]
    PermShkPrbs = PermShkDstn[0]
    PermShkVals  = PermShkDstn[1]        
    TranShkCount  = TranShkPrbs.size
    PermShkCount = PermShkPrbs.size
    uPinv = lambda X : CRRAutilityP_inv(X,gam=CRRA)

    # Make tiled versions of the grid of a_t values and the components of the shock distribution
    aXtraCount = aXtraGrid.size    # = 200 
    bNrmGrid_rep = np.tile(np.reshape(aXtraGrid,(aXtraCount,1)),(1,TranShkCount)) # Replicated axtraGrid of b_t values (bNowGrid) for each transitory (productivity) shock
    TranShkVals_rep = np.tile(np.reshape(TranShkVals,(1,TranShkCount)),(aXtraCount,1)) # Replicated transitory shock values for each b_t state
    TranShkPrbs_rep = np.tile(np.reshape(TranShkPrbs,(1,TranShkCount)),(aXtraCount,1)) # Replicated transitory shock probabilities for each b_t state
    
    # Calculate marginal value next period for each gridpoint and each transitory shock    
    bNext = Rfree * bNrmGrid_rep  # Next period's bank balances. (200,16)    
    vPNext = vPfunc_next(bNext, TranShkVals_rep) # Derive the Next period's marginal value at every transitory shock and every bank balances gridpoint           
    vPbarNext = np.sum(vPNext*TranShkPrbs_rep, axis = 1) # Integrate out the transitory shocks (in TranShkVals direction)
    vPbarNvrsNext = uPinv(vPbarNext) # Marginal value transformed through the inverse marginal utility function
    vPbarNvrsFuncNext = LinearInterp(np.insert(bNext[:,0],0,0.0),np.insert(vPbarNvrsNext,0,0.0)) # Linear interpolation over the b_t. Add a point at b_t = 0. 
    vPbarFuncNext = MargValueFunc(vPbarNvrsFuncNext,CRRA)   # Take the marginal utility function to inverse back and get the optimal values for consumption

    # Get the next period's bank balances at each permanent shock
    aNrmGrid_rep = np.tile(np.reshape(aXtraGrid,(aXtraCount,1)),(1,PermShkCount)) # Replicated axtraGrid of b_t values (bNowGrid) for each permanent (productivity) shock. (200,16)   
    PermShkVals_rep = np.tile(np.reshape(PermShkVals,(1,PermShkCount)),(aXtraCount,1)) # Replicated permanent shock values for each b_t state   
    PermShkPrbs_rep = np.tile(np.reshape(PermShkPrbs,(1,PermShkCount)),(aXtraCount,1)) # Replicated permanent shock probabilities for each b_t state
    bNextPerm = (Rfree/(PermGroFac*PermShkVals_rep))*aNrmGrid_rep     # (200,16)

    ''' 3/ '''
    # Construct the marginal value of end-of-period assets  
    EndOfPrdvP_temp = DiscFac*Rfree*LivPrb*np.sum((PermGroFac*PermShkVals_rep)**(-CRRA)*vPbarFuncNext(bNextPerm)*PermShkPrbs_rep,axis=1) # sum in the TranShkVals ~ TranShkGrid direction
    EndOfPrdvP = EndOfPrdvP_temp.reshape((aXtraCount,1))   # ---- Convert it to a (row? Notes) column vector of size (200,1)  
    TranShkScaleFac_temp = frac*(WageRte*TranShkGrid)**(LbrCost*frac)*(LbrCost**(-LbrCost*frac)+LbrCost**(frac))   
    TranShkScaleFac = TranShkScaleFac_temp.reshape((1,TranShkGrid.size))   # --- Convert it to a row (column?) vector of size (1,16)
   
    ''' 4/ ''' 
    xNowArray = (np.dot(EndOfPrdvP,TranShkScaleFac))**(-1./(CRRA-LbrCost*frac))    #(200,16) Get an array of x_t values corresponding to (a_t,theta_t) values   
    
    ''' 5/: Error raising xNowArray to a non-integer power, frac, 1/ (1+0.36) Or NAN array'''
    TranShkGrid_rep = np.tile(np.reshape(TranShkGrid,(1,TranShkGrid.size)),(aXtraCount,1))
    xNowPowered = xNowArray**frac
    cNrmNow = (((WageRte*TranShkGrid_rep)/LbrCost)**(LbrCost*frac))*xNowPowered # Find optimal consumption using the solution to the effective consumption pb
    LsrNow = (LbrCost/(WageRte*TranShkGrid_rep))**frac*xNowPowered # Find optimal leisure amount using the solution to the effective consumption pb
    cNrmNow[:,0] = uPinv(EndOfPrdvP_temp)
    LsrNow[:,0] = 1.0

    # Check the Labor Constraint using violatesLbrCnst: boolean array. An indicator for whether 
    # the labor constraint is violated or not. The Agent cannot choose to work a negative amount of time. Labor = 1 - Leisure
    violates_labor_constraint = LsrNow > 1.
    EndOfPrdvP_temp = np.tile(np.reshape(EndOfPrdvP,(aXtraCount,1)),(1,TranShkCount))
    cNrmNow[violates_labor_constraint] = uPinv(EndOfPrdvP_temp[violates_labor_constraint])
    LsrNow[violates_labor_constraint] = 1.   # Set up z =1, upper limit

    '''6/'''
    aNrmNow_rep = np.tile(np.reshape(aXtraGrid,(aXtraCount,1)),(1,TranShkGrid.size))
    bNrmNow = aNrmNow_rep - WageRte*TranShkGrid_rep + cNrmNow + WageRte*TranShkGrid_rep*LsrNow
    bNowExtra = np.reshape(-WageRte*TranShkGrid,(1,TranShkGrid.size))   # bank balances when c_t = 0 and z_t=0, column vector of (16,)    
    bNowArray = np.concatenate((bNowExtra, bNrmNow),axis=0)    # ***-- Combine the two pieces of the b_t grid (when c_t=0, z_t=0 and following grid) 
    
    cNowArray = np.concatenate((np.zeros((1,TranShkGrid.size)),cNrmNow),axis=0) # ----
    LsrNowArray = np.concatenate((np.zeros((1,TranShkGrid.size)),LsrNow),axis=0)
    LsrNowArray[0,0] = 1.0 # Don't work at all if TranShk=0, even if bNrm=0
    LbrNowArray = 1. - LsrNowArray # Labor is the complement of leisure
    
    '''7'''
    # Get the (pseudo-inverse) marginal value using end of period marginal value
    vPnvrsNow = uPinv(EndOfPrdvP_temp) # a column vector (200,) or (200,1) with EndOfPrdvP
    vPnvrsNowArray = np.concatenate((np.zeros((1,TranShkGrid.size)), vPnvrsNow)) # Concatenate a column vector of zeros on the left edge

    # Construct consumption and marginal value functions for this period
    '''8/ '''
    bNrmMinNow = LinearInterp(TranShkGrid,bNowArray[0,:])

    ''' 9/ '''
    # Loop over each transitory shock and make a linear interpolation to get lists of optimal consumption, labor and (pseudo-inverse) marginal value
    cFuncNow_list = []    # Initialize the empty list of 1D function
    LbrFuncNow_list = []
    vPnvrsFuncNow_list = []
    for j in range(TranShkGrid.size):                   
        # Adjust bNrmNow for this transitory shock
        bNrmNow_temp = bNowArray[:,j] - bNowArray[0,j]
        cFuncNow_list.append(LinearInterp(bNrmNow_temp,cNowArray[:,j])) # Make consumption function for this transitory shock
        LbrFuncNow_list.append(LinearInterp(bNrmNow_temp,LbrNowArray[:,j])) # Make labor function for this transitory shock
        vPnvrsFuncNow_list.append(LinearInterp(bNrmNow_temp,vPnvrsNowArray[:,j])) # Make pseudo-inverse marginal value function for this transitory shock

    '''10'''
    # Make linear interpolation by combining the lists of consumption, labor and marginal value functions
    cFuncNowBase = LinearInterpOnInterp1D(cFuncNow_list,TranShkGrid)
    LbrFuncNowBase = LinearInterpOnInterp1D(LbrFuncNow_list,TranShkGrid)
    vPnvrsFuncNowBase = LinearInterpOnInterp1D(vPnvrsFuncNow_list,TranShkGrid)
    
    '''11'''
    # Construct consumption, labor, marginal value functions with bNrmMinNow as the lower bound
    cFuncNow = VariableLowerBoundFunc2D(cFuncNowBase,bNrmMinNow)
    LbrFuncNow = VariableLowerBoundFunc2D(LbrFuncNowBase,bNrmMinNow)
    vPnvrsFuncNow = VariableLowerBoundFunc2D(vPnvrsFuncNowBase,bNrmMinNow)
     
    '''12'''
    # Construct the marginal value function using the envelope condition
    vPfuncNow = MargValueFunc2D(vPnvrsFuncNow,CRRA)  

    '''13'''
    # Make a solution object for this period and return it
    solution = ConsumerLaborSolution(cFunc=cFuncNow,LbrFunc=LbrFuncNow,vPfunc=vPfuncNow,bNrmMin=bNrmMinNow)
    return solution

        
class LaborIntMargConsumerType(IndShockConsumerType):
    
    '''        
    A class for representing an ex ante homogeneous type of consumer in the
    consumption-saving model.  These consumers have CRRA utility over current
    consumption and discount future utility exponentially.  Their future income
    is subject to transitory  and permanent shocks, and they can earn gross interest
    on retained assets at a risk free interest factor.  
    
    The solution is represented in a normalized way, with all variables divided 
    by permanent income (raised to the appropriate power). 
    
    This model is homothetic in permanent income.
    
    IndShockConsumerType:  A consumer type with idiosyncratic shocks to permanent and transitory income.
    His problem is defined by a sequence of income distributions, survival probabilities, 
    and permanent income growth rates, as well as time invariant values for risk aversion, 
    discount factor, the interest rate, the grid of end-of-period assets, and an artificial borrowing constraint.
    '''
    time_vary_ = copy(IndShockConsumerType.time_vary_)
    time_vary_ += ['LbrCost','WageRte']
    time_inv_ = copy(IndShockConsumerType.time_inv_)
    
    def __init__(self,cycles=1,time_flow=True,**kwds):
        '''
        Instantiate a new consumer type with given data.
        See ConsumerParameters.init_labor_intensive for a dictionary of
        the keywords that should be passed to the constructor.
        
        Parameters
        ----------
        cycles : int
            Number of times the sequence of periods should be solved.
        time_flow : boolean
            Whether time is currently "flowing" forward for this instance.
        
        Returns
        -------
        None
        '''  
        IndShockConsumerType.__init__(self,cycles = cycles,time_flow=time_flow,**kwds)
        self.pseudo_terminal = False
        self.solveOnePeriod = solveConsLaborIntMarg
        self.update()
    
    
    def update(self):
        '''
        Update the income process, the assets grid, and the terminal solution.
        
        Parameters
        ----------
        None
        
        Returns
        -------
        None
        '''
        self.updateIncomeProcess()
        self.updateAssetsGrid()
        self.updateTranShkGrid()
        
 
    def calcBoundingValues(self):      
        '''
        Calculate human wealth plus minimum and maximum MPC in an infinite
        horizon model with only one period repeated indefinitely.  Store results
        as attributes of self.  Human wealth is the present discounted value of
        expected future income after receiving income this period, ignoring mort-
        ality.  The maximum MPC is the limit of the MPC as m --> mNrmMin.  The
        minimum MPC is the limit of the MPC as m --> infty.
        
        NOT YET IMPLEMENTED FOR THIS CLASS
        
        Parameters
        ----------
        None
        
        Returns
        -------
        None
        '''
        raise NotImplementedError()
        
    def makeEulerErrorFunc(self,mMax=100,approx_inc_dstn=True):
        '''
        Creates a "normalized Euler error" function for this instance, mapping
        from market resources to "consumption error per dollar of consumption."
        Stores result in attribute eulerErrorFunc as an interpolated function.
        Has option to use approximate income distribution stored in self.IncomeDstn
        or to use a (temporary) very dense approximation.
        
        NOT YET IMPLEMENTED FOR THIS CLASS
        
        Parameters
        ----------
        mMax : float
            Maximum normalized market resources for the Euler error function.
        approx_inc_dstn : Boolean
            Indicator for whether to use the approximate discrete income distri-
            bution stored in self.IncomeDstn[0], or to use a very accurate
            discrete approximation instead.  When True, uses approximation in
            IncomeDstn; when False, makes and uses a very dense approximation.
        
        Returns
        -------
        None
        '''
        raise NotImplementedError()


    def updateTranShkGrid(self):
        ''' Create a list of values for TranShkGrid using TranShkVals, index 1 of TranShkDstn
        
        Parameters
        ----------
        none
        
        Returns
        -------
        none
        '''
        time_orig=self.time_flow
        self.timeFwd()
      
        TranShkGrid = []   # Create an empty list for TranShkGrid that will be updated
        for t in range(self.T_cycle):
            TranShkGrid.append(self.TranShkDstn[t][1])  # Update/ Extend the list of TranShkGrid with the TranShkVals for each TranShkPrbs
        self.TranShkGrid = TranShkGrid  # Save that list in self (time-varying)
        self.addToTimeVary('TranShkGrid')   # Run the method addToTimeVary from AgentType to add TranShkGrid as one parameter of time_vary list
        
        if not time_orig:
            self.timeRev()
            
     
    def updateSolutionTerminal(self):
        ''' 
        Updates the terminal period solution and solves for optimal consumption and labor when there is no future.
        
        
        Parameters
        ----------
        None
            
        Returns
        -------
        None
        '''   
        if self.time_flow:   # To make sure we pick the last element of the list, depending on the direction time is flowing
            t=-1
        else:
            t=0
        TranShkGrid = self.TranShkGrid[t]
        LbrCost = self.LbrCost[t]
        WageRte = self.WageRte[t]

        bNrmGrid = np.insert(self.aXtraGrid,0,0.0) # Add a point at b_t = 0 to make sure that bNrmGrid goes down to 0
        bNrmCount = bNrmGrid.size   # 201
        TranShkCount = TranShkGrid.size     # = (7,)   
        bNrmGridTerm = np.tile(np.reshape(bNrmGrid,(bNrmCount,1)),(1,TranShkCount)) # Replicated bNrmGrid for each transitory shock theta_t      
        TranShkGridTerm = np.tile(TranShkGrid,(bNrmCount,1))    # Tile the grid of transitory shocks for the terminal solution. (201,7)  
                                               
        # Array of labor (leisure) values for terminal solution
        LsrTerm = np.minimum((LbrCost/(1.+LbrCost))*(bNrmGridTerm/(WageRte*TranShkGridTerm)+1.),1.0)
        LsrTerm[0,0] = 1.0
        LbrTerm = 1.0 - LsrTerm
        
        # Calculate market resources in terminal period, which is consumption
        mNrmTerm = bNrmGridTerm + LbrTerm*WageRte*TranShkGridTerm
        cNrmTerm = mNrmTerm # Consume everything we have
        
        # Make a bilinear interpolation to represent the labor and consumption functions
        LbrFunc_terminal = BilinearInterp(LbrTerm,bNrmGrid,TranShkGrid)
        cFunc_terminal = BilinearInterp(cNrmTerm,bNrmGrid,TranShkGrid)
        
        # Compute the effective consumption value using consumption value and labor value at the terminal solution
        xEffTerm = LsrTerm**LbrCost*cNrmTerm
        vNvrsFunc_terminal = BilinearInterp(xEffTerm,bNrmGrid,TranShkGrid)
        vFunc_terminal = ValueFunc2D(vNvrsFunc_terminal, self.CRRA)
        
        # Using the envelope condition at the terminal solution to estimate the marginal value function      
        vPterm = LsrTerm**LbrCost*CRRAutilityP(xEffTerm,gam=self.CRRA)        
        vPnvrsTerm = CRRAutilityP_inv(vPterm,gam=self.CRRA)     # Evaluate the inverse of the CRRA marginal utility function at a given marginal value, vP
        
        vPnvrsFunc_terminal = BilinearInterp(vPnvrsTerm,bNrmGrid,TranShkGrid)
        vPfunc_terminal = MargValueFunc2D(vPnvrsFunc_terminal,self.CRRA) # Get the Marginal Value function
            
        bNrmMin_terminal = ConstantFunction(0.)     # Trivial function that return the same real output for any input
        
        self.solution_terminal = ConsumerLaborSolution(cFunc=cFunc_terminal,LbrFunc=LbrFunc_terminal,\
                                 vFunc=vFunc_terminal,vPfunc=vPfunc_terminal,bNrmMin=bNrmMin_terminal)
        
        
    def plotcFunc(self,t,bMin=None,bMax=None,ShkSet=None):
        '''
        Plot the consumption function by bank balances at a given set of transitory shocks.
        
        Parameters
        ----------
        t : int
            Time index of the solution for which to plot the consumption function.
        bMin : float or None
            Minimum value of bNrm at which to begin the plot.  If None, defaults
            to the minimum allowable value of bNrm for each transitory shock.
        bMax : float or None
            Maximum value of bNrm at which to end the plot.  If None, defaults
            to bMin + 20.
        ShkSet : [float] or None
            Array or list of transitory shocks at which to plot the consumption
            function.  If None, defaults to the TranShkGrid for this time period.
        
        Returns
        -------
        None
        '''
        if ShkSet is None:
            ShkSet = self.TranShkGrid[t]
        if bMin is None:
            bMinSet = self.solution[0].bNrmMin(TranShkSet)
        else:
            bMinSet = bMin*np.ones_like(TranShkSet)
        if bMax is None:
            bMaxSet = bMinSet + 20.
        else:
            bMaxSet = bMax*np.ones_like(TranShkSet)
             
        for j in range(len(ShkSet)):
            Shk = ShkSet[j]
            B = np.linspace(bMinSet[j],bMaxSet[j],300)
            C = LaborIntMargExample.solution[t].cFunc(B,Shk*np.ones_like(B))
            plt.plot(B,C)
        plt.xlabel('Beginning of period bank balances')
        plt.ylabel('Normalized consumption level')
        plt.show()
       
               
###############################################################################
          
if __name__ == '__main__':
    import ConsumerParametersTM as Params    # Parameters for a consumer type
    import matplotlib.pyplot as plt
    from time import clock
    mystr = lambda number : "{:.4f}".format(number)     # Format numbers as strings
    
    # Make and solve a labor intensive margin consumer i.e. a consumer with utility for leisure
    LaborIntMargExample = LaborIntMargConsumerType(**Params.init_labor_intensive)
    LaborIntMargExample.cycles = 0
    
    t_start = clock()
    LaborIntMargExample.solve()
    t_end = clock()
    print('Solving a labor intensive margin consumer took ' + str(t_end-t_start) + ' seconds.')
    
    t = 0
    bMax = 100.
    
    # Plot the consumption function at various transitory productivity shocks
    TranShkSet = LaborIntMargExample.TranShkGrid[t]
    B = np.linspace(0.,bMax,300)
    for Shk in TranShkSet:
        B_temp = B + LaborIntMargExample.solution[t].bNrmMin(Shk)
        C = LaborIntMargExample.solution[t].cFunc(B_temp,Shk*np.ones_like(B_temp))
        plt.plot(B_temp,C)
    plt.xlabel('Beginning of period bank balances')
    plt.ylabel('Normalized consumption level')
    plt.show()
    
    # Plot the marginal consumption function at various transitory productivity shocks
    TranShkSet = LaborIntMargExample.TranShkGrid[t]
    B = np.linspace(0.,bMax,300)
    for Shk in TranShkSet:
        B_temp = B + LaborIntMargExample.solution[t].bNrmMin(Shk)
        C = LaborIntMargExample.solution[t].cFunc.derivativeX(B_temp,Shk*np.ones_like(B_temp))
        plt.plot(B_temp,C)
    plt.xlabel('Beginning of period bank balances')
    plt.ylabel('Marginal propensity to consume')
    plt.show()
    
    # Plot the labor function at various transitory productivity shocks
    TranShkSet = LaborIntMargExample.TranShkGrid[t]
    B = np.linspace(0.,bMax,300)
    for Shk in TranShkSet:
        B_temp = B + LaborIntMargExample.solution[t].bNrmMin(Shk)
        Lbr = LaborIntMargExample.solution[t].LbrFunc(B_temp,Shk*np.ones_like(B_temp))
        plt.plot(B_temp,Lbr)
    plt.xlabel('Beginning of period bank balances')
    plt.ylabel('Labor supply')
    plt.show()
    
    # Plot the marginal value function at various transitory productivity shocks
    pseudo_inverse = True
    TranShkSet = LaborIntMargExample.TranShkGrid[t]
    B = np.linspace(0.,bMax,300)
    for Shk in TranShkSet:
        B_temp = B + LaborIntMargExample.solution[t].bNrmMin(Shk)
        if pseudo_inverse:
            vP = LaborIntMargExample.solution[t].vPfunc.cFunc(B_temp,Shk*np.ones_like(B_temp))
        else:
            vP = LaborIntMargExample.solution[t].vPfunc(B_temp,Shk*np.ones_like(B_temp))
        plt.plot(B_temp,vP)
    plt.xlabel('Beginning of period bank balances')
    if pseudo_inverse:
        plt.ylabel('Pseudo inverse marginal value')
    else:
        plt.ylabel('Marginal value')
    plt.show()
    